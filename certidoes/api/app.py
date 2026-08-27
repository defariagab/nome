"""Servidor da aplicação: API + painel web."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import Body, FastAPI, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import agenda, arquivos, catalogo, nomeacao, servicos
from ..automacao import desafios
from ..banco import iniciar, sessao
from ..config import config
from ..fila import fila
from ..modelos import (
    Certidao, Desafio, EstadoDesafio, EstadoSolicitacao, Evento, Monitoramento,
    Solicitacao, TipoCertidao, Titular, agora,
)
from ..validade import Status
from . import serializacao

log = logging.getLogger("certidoes.api")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    iniciar()
    catalogo.carregar()
    fila.iniciar()
    import asyncio

    tarefa_agenda = asyncio.create_task(agenda.rodar_periodicamente())
    try:
        yield
    finally:
        tarefa_agenda.cancel()
        await fila.parar()


app = FastAPI(title="Certidões", version="0.1.0", lifespan=ciclo_de_vida)


@app.exception_handler(servicos.ErroDeUso)
async def _erro_de_uso(_request, erro: servicos.ErroDeUso):
    return JSONResponse(status_code=400, content={"erro": str(erro)})


def _nomes(s, titular_id: int, tipo_id: int) -> tuple[str, str]:
    titular = s.get(Titular, titular_id)
    tipo = s.get(TipoCertidao, tipo_id)
    return (titular.nome if titular else ""), (tipo.nome if tipo else "")


def _data(texto: str | None) -> date | None:
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        raise servicos.ErroDeUso("Data inválida. Use o formato dia/mês/ano.")


# --------------------------------------------------------------------------- #
# Painel
# --------------------------------------------------------------------------- #

@app.get("/api/resumo")
def ler_resumo():
    with sessao() as s:
        dados = servicos.resumo(s)
    dados["motor"] = config.motor
    dados["modo_demonstracao"] = config.motor == "simulador"
    return dados


@app.get("/api/painel")
def ler_painel(titular_id: int | None = None, status: str | None = None):
    with sessao() as s:
        linhas = servicos.painel(s, titular_id=titular_id)
    if status:
        pedidos = set(status.split(","))
        linhas = [l for l in linhas if l["status"] in pedidos]
    return linhas


# --------------------------------------------------------------------------- #
# Titulares
# --------------------------------------------------------------------------- #

class DadosTitular(BaseModel):
    nome: str
    documento: str
    inscricao_estadual: str | None = None
    uf: str | None = None
    municipio: str | None = None
    codigo_ibge: str | None = None
    email: str | None = None
    observacoes: str | None = None
    ativo: bool = True
    monitoramentos: list[int] = Field(default_factory=list)
    dias_antecedencia: int = 15
    renovar_automaticamente: bool = True


def _monitorados(s, titular_id: int) -> list[int]:
    return list(s.scalars(
        select(Monitoramento.tipo_certidao_id).where(
            Monitoramento.titular_id == titular_id, Monitoramento.ativo
        )
    ))


@app.get("/api/titulares")
def listar_titulares(incluir_inativos: bool = False):
    with sessao() as s:
        consulta = select(Titular).order_by(Titular.nome)
        if not incluir_inativos:
            consulta = consulta.where(Titular.ativo)
        return [serializacao.titular(t, _monitorados(s, t.id)) for t in s.scalars(consulta)]


@app.get("/api/titulares/{titular_id}")
def ler_titular(titular_id: int):
    with sessao() as s:
        titular = s.get(Titular, titular_id)
        if titular is None:
            raise HTTPException(404, "Titular não encontrado.")
        return serializacao.titular(titular, _monitorados(s, titular_id))


@app.post("/api/titulares")
def criar_titular(dados: DadosTitular):
    with sessao() as s:
        titular = servicos.salvar_titular(s, dados.model_dump())
        servicos.definir_monitoramentos(
            s, titular.id, dados.monitoramentos, dados.dias_antecedencia, dados.renovar_automaticamente
        )
        s.flush()
        return serializacao.titular(titular, list(dados.monitoramentos))


@app.put("/api/titulares/{titular_id}")
def atualizar_titular(titular_id: int, dados: DadosTitular):
    with sessao() as s:
        titular = servicos.salvar_titular(s, dados.model_dump(), titular_id)
        servicos.definir_monitoramentos(
            s, titular.id, dados.monitoramentos, dados.dias_antecedencia, dados.renovar_automaticamente
        )
        s.flush()
        return serializacao.titular(titular, list(dados.monitoramentos))


@app.delete("/api/titulares/{titular_id}")
def desativar_titular(titular_id: int):
    """Desativa sem apagar: o acervo de certidões é prova e deve ser preservado."""
    with sessao() as s:
        titular = s.get(Titular, titular_id)
        if titular is None:
            raise HTTPException(404, "Titular não encontrado.")
        titular.ativo = False
        servicos.registrar_evento(s, "titular", titular_id, "desativado", f"{titular.nome} desativado.")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Catálogo
# --------------------------------------------------------------------------- #

class AjusteTipo(BaseModel):
    url: str | None = None
    validade_dias: int | None = None
    observacoes: str | None = None
    ativo: bool | None = None


#: as federais valem para todo mundo e são as mais pedidas: vêm primeiro
ORDEM_DAS_ESFERAS = {"federal": 0, "estadual": 1, "municipal": 2}


@app.get("/api/tipos")
def listar_tipos():
    with sessao() as s:
        tipos = [serializacao.tipo(t) for t in s.scalars(select(TipoCertidao))]
    tipos.sort(key=lambda t: (ORDEM_DAS_ESFERAS.get(t["esfera"], 9), t["nome"]))
    return tipos


@app.put("/api/tipos/{tipo_id}")
def ajustar_tipo(tipo_id: int, dados: AjusteTipo):
    with sessao() as s:
        tipo = s.get(TipoCertidao, tipo_id)
        if tipo is None:
            raise HTTPException(404, "Tipo não encontrado.")
        if dados.url is not None:
            tipo.url = dados.url.strip()
        if dados.validade_dias is not None:
            if dados.validade_dias <= 0:
                raise servicos.ErroDeUso("A validade deve ser maior que zero.")
            tipo.validade_dias = dados.validade_dias
        if dados.observacoes is not None:
            tipo.observacoes = dados.observacoes
        if dados.ativo is not None:
            tipo.ativo = dados.ativo
        s.flush()
        return serializacao.tipo(tipo)


# --------------------------------------------------------------------------- #
# Solicitações
# --------------------------------------------------------------------------- #

class PedidoEmissao(BaseModel):
    titular_id: int
    tipo_id: int


@app.post("/api/solicitacoes")
def criar_solicitacao(pedido: PedidoEmissao):
    with sessao() as s:
        solicitacao = servicos.solicitar(s, pedido.titular_id, pedido.tipo_id)
        nomes = _nomes(s, solicitacao.titular_id, solicitacao.tipo_certidao_id)
        return serializacao.solicitacao(solicitacao, *nomes)


@app.post("/api/solicitacoes/pendentes")
def solicitar_pendentes():
    """Coloca na fila tudo o que está vencido, vencendo ou nunca emitido."""
    alvos = {Status.VENCIDA.value, Status.AUSENTE.value, Status.VENCE_EM_BREVE.value}
    criadas = []
    with sessao() as s:
        for linha in servicos.painel(s):
            if linha["status"] in alvos and not linha["solicitacao_em_andamento"]:
                criadas.append(servicos.solicitar(s, linha["titular_id"], linha["tipo_id"]).id)
    return {"criadas": len(criadas), "ids": criadas}


@app.get("/api/solicitacoes")
def listar_solicitacoes(estado: str | None = None, limite: int = Query(50, le=200)):
    with sessao() as s:
        consulta = select(Solicitacao).order_by(Solicitacao.id.desc()).limit(limite)
        if estado:
            consulta = consulta.where(Solicitacao.estado.in_([EstadoSolicitacao(e) for e in estado.split(",")]))
        return [
            serializacao.solicitacao(x, *_nomes(s, x.titular_id, x.tipo_certidao_id))
            for x in s.scalars(consulta)
        ]


@app.get("/api/solicitacoes/{solicitacao_id}")
def ler_solicitacao(solicitacao_id: int):
    with sessao() as s:
        solicitacao = s.get(Solicitacao, solicitacao_id)
        if solicitacao is None:
            raise HTTPException(404, "Solicitação não encontrada.")
        return serializacao.solicitacao(
            solicitacao, *_nomes(s, solicitacao.titular_id, solicitacao.tipo_certidao_id)
        )


@app.post("/api/solicitacoes/{solicitacao_id}/cancelar")
def cancelar_solicitacao(solicitacao_id: int):
    desafios.cancelar_abertos(solicitacao_id)
    with sessao() as s:
        solicitacao = s.get(Solicitacao, solicitacao_id)
        if solicitacao is None:
            raise HTTPException(404, "Solicitação não encontrada.")
        if solicitacao.estado.encerrada:
            raise servicos.ErroDeUso("Esta solicitação já foi encerrada.")
        solicitacao.estado = EstadoSolicitacao.CANCELADA
        solicitacao.concluida_em = agora()
        solicitacao.mensagem = "Cancelada pelo usuário."
    return {"ok": True}


@app.post("/api/solicitacoes/{solicitacao_id}/reenviar")
def reenviar_solicitacao(solicitacao_id: int):
    with sessao() as s:
        anterior = s.get(Solicitacao, solicitacao_id)
        if anterior is None:
            raise HTTPException(404, "Solicitação não encontrada.")
        nova = servicos.solicitar(s, anterior.titular_id, anterior.tipo_certidao_id)
        return serializacao.solicitacao(nova, *_nomes(s, nova.titular_id, nova.tipo_certidao_id))


@app.post("/api/solicitacoes/{solicitacao_id}/anexar")
async def anexar(
    solicitacao_id: int,
    arquivo: UploadFile,
    emitida_em: str | None = None,
    valida_ate: str | None = None,
):
    dados = await arquivo.read()
    if len(dados) > 25 * 1024 * 1024:
        raise servicos.ErroDeUso("O arquivo é grande demais (limite de 25 MB).")
    with sessao() as s:
        certidao = servicos.anexar_documento(
            s, solicitacao_id, dados, _data(emitida_em), _data(valida_ate)
        )
        return serializacao.certidao(certidao, *_nomes(s, certidao.titular_id, certidao.tipo_certidao_id))


# --------------------------------------------------------------------------- #
# Desafios (captcha, login, ação manual)
# --------------------------------------------------------------------------- #

@app.get("/api/desafios")
def listar_desafios():
    with sessao() as s:
        consulta = (
            select(Desafio).where(Desafio.estado == EstadoDesafio.ABERTO).order_by(Desafio.id)
        )
        saida = []
        for desafio in s.scalars(consulta):
            solicitacao = s.get(Solicitacao, desafio.solicitacao_id)
            nomes = _nomes(s, solicitacao.titular_id, solicitacao.tipo_certidao_id) if solicitacao else ("", "")
            saida.append(serializacao.desafio(desafio, *nomes))
        return saida


@app.post("/api/desafios/{desafio_id}/responder")
def responder_desafio(resposta: str = Body("", embed=True), desafio_id: int = 0):
    if not desafios.responder(desafio_id, resposta):
        raise servicos.ErroDeUso("Este pedido já foi respondido ou expirou.")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Acervo
# --------------------------------------------------------------------------- #

@app.get("/api/certidoes")
def listar_certidoes(titular_id: int | None = None, incluir_substituidas: bool = False,
                     limite: int = Query(200, le=500)):
    with sessao() as s:
        consulta = select(Certidao).order_by(Certidao.valida_ate.desc(), Certidao.id.desc()).limit(limite)
        if titular_id:
            consulta = consulta.where(Certidao.titular_id == titular_id)
        if not incluir_substituidas:
            consulta = consulta.where(Certidao.substituida.is_(False))
        return [
            serializacao.certidao(c, *_nomes(s, c.titular_id, c.tipo_certidao_id))
            for c in s.scalars(consulta)
        ]


@app.get("/api/certidoes/{certidao_id}/arquivo")
def baixar_certidao(certidao_id: int):
    with sessao() as s:
        certidao = s.get(Certidao, certidao_id)
        if certidao is None or not certidao.arquivo:
            raise HTTPException(404, "Documento não encontrado.")
        titular = s.get(Titular, certidao.titular_id)
        tipo = s.get(TipoCertidao, certidao.tipo_certidao_id)
        caminho = arquivos.caminho_absoluto(certidao.arquivo)
        if not caminho.exists():
            raise HTTPException(404, "O arquivo não está mais na pasta de documentos.")
        nome = f"{tipo.codigo}_{titular.documento}_{certidao.emitida_em.isoformat()}.pdf"
        return FileResponse(caminho, media_type="application/pdf", filename=nome)


@app.get("/api/titulares/{titular_id}/dossie")
def baixar_dossie(titular_id: int):
    """Um PDF único com as certidões vigentes — o que a licitação pede."""
    from ..dossie import SemCertidoes, montar

    with sessao() as s:
        try:
            conteudo, nome = montar(s, titular_id)
        except SemCertidoes as erro:
            raise servicos.ErroDeUso(str(erro)) from erro
        servicos.registrar_evento(s, "titular", titular_id, "dossie", "Dossiê de regularidade gerado.")
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@app.get("/api/eventos")
def listar_eventos(limite: int = Query(50, le=200)):
    with sessao() as s:
        consulta = select(Evento).order_by(Evento.id.desc()).limit(limite)
        return [serializacao.evento(e) for e in s.scalars(consulta)]


@app.post("/api/renovacao/varrer")
def varrer_renovacoes():
    return {"criadas": len(agenda.varrer())}


# --------------------------------------------------------------------------- #
# Preferências do escritório
# --------------------------------------------------------------------------- #

class Preferencias(BaseModel):
    padrao_nome_arquivo: str


@app.get("/api/preferencias")
def ler_preferencias():
    with sessao() as s:
        padrao = servicos.preferencia(s, "padrao_nome_arquivo", nomeacao.PADRAO)
    return {
        "padrao_nome_arquivo": padrao,
        "padrao_do_sistema": nomeacao.PADRAO,
        "exemplo": nomeacao.exemplo(padrao),
        "campos": nomeacao.CAMPOS,
        "paralelismo": config.paralelismo,
    }


@app.put("/api/preferencias")
def salvar_preferencias(dados: Preferencias):
    try:
        padrao = nomeacao.validar(dados.padrao_nome_arquivo)
    except ValueError as erro:
        raise servicos.ErroDeUso(str(erro)) from erro
    with sessao() as s:
        servicos.definir_preferencia(s, "padrao_nome_arquivo", padrao)
    return {"padrao_nome_arquivo": padrao, "exemplo": nomeacao.exemplo(padrao)}


class PedidoConferencia(BaseModel):
    codigos: list[str] = Field(default_factory=list)
    #: mostrar a janela do navegador enquanto confere
    visivel: bool = False


@app.post("/api/diagnostico")
async def conferir_receitas(pedido: PedidoConferencia):
    """Percorre as receitas nos sites reais, sem emitir nada, e guarda o relatório."""
    from ..diagnostico import conferir_todas, salvar_relatorio

    try:
        relatorio = await conferir_todas(pedido.codigos or None, visivel=pedido.visivel)
    except Exception as erro:
        raise servicos.ErroDeUso(
            f"Não consegui conferir as receitas: {erro}. Confira se o navegador do "
            "Playwright está instalado."
        ) from erro
    caminho = salvar_relatorio(relatorio)
    relatorio["arquivo"] = caminho.name
    return relatorio


@app.get("/api/diagnostico/relatorio")
def baixar_relatorio():
    """Entrega o relatório mais recente, para enviar a quem vai corrigir a receita."""
    pasta = config.pasta_dados / "diagnostico"
    arquivos_md = sorted(pasta.glob("conferencia-*.md")) if pasta.exists() else []
    if not arquivos_md:
        raise HTTPException(404, "Nenhuma conferência foi feita ainda.")
    return FileResponse(
        arquivos_md[-1], media_type="text/markdown", filename=arquivos_md[-1].name
    )


class PedidoInspecao(BaseModel):
    url: str
    espera: int = 0


@app.post("/api/inspecionar")
async def inspecionar_site(pedido: PedidoInspecao):
    """Abre o site do órgão e lista os campos, para montar/corrigir a receita."""
    if not pedido.url.startswith(("http://", "https://")):
        raise servicos.ErroDeUso("Informe o endereço completo, começando com https://")
    from ..automacao.inspecao import inspecionar

    try:
        return await inspecionar(pedido.url, espera=min(max(pedido.espera, 0), 300))
    except Exception as erro:
        raise servicos.ErroDeUso(
            f"Não consegui abrir a página: {erro}. Confira o endereço e se o navegador "
            "do Playwright está instalado."
        ) from erro


@app.get("/api/saude")
def saude():
    return {"ok": True, "versao": app.version, "motor": config.motor}


# --------------------------------------------------------------------------- #
# Painel web
# --------------------------------------------------------------------------- #

@app.get("/")
def raiz():
    return FileResponse(config.pasta_web / "index.html")


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


app.mount("/web", StaticFiles(directory=config.pasta_web), name="web")
