"""Regras de aplicação: o que o painel e a API usam."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import arquivos, nomeacao
from .automacao.extracao import analisar
from .documento import apenas_digitos, formatar, tipo_pessoa, valido
from .modelos import (  # noqa: F401  (Titular é reexportado para conveniência)
    Certidao, Configuracao, Desafio, EstadoDesafio, EstadoSolicitacao, Evento,
    Monitoramento, SituacaoCertidao, Solicitacao, TipoCertidao, TipoPessoa, Titular, agora,
)
from .validade import Status, avaliar, calcular_validade


class ErroDeUso(ValueError):
    """Erro previsto, com mensagem escrita para o usuário final."""


# --------------------------------------------------------------------------- #
# Preferências do escritório
# --------------------------------------------------------------------------- #

def preferencia(s: Session, chave: str, padrao: str = "") -> str:
    registro = s.get(Configuracao, chave)
    return registro.valor if registro else padrao


def definir_preferencia(s: Session, chave: str, valor: str) -> None:
    if registro := s.get(Configuracao, chave):
        registro.valor = valor
    else:
        s.add(Configuracao(chave=chave, valor=valor))


# --------------------------------------------------------------------------- #
# Auditoria
# --------------------------------------------------------------------------- #

def registrar_evento(s: Session, entidade: str, entidade_id: int | None, tipo: str, mensagem: str) -> None:
    s.add(Evento(entidade=entidade, entidade_id=entidade_id, tipo=tipo, mensagem=mensagem))


# --------------------------------------------------------------------------- #
# Titulares
# --------------------------------------------------------------------------- #

def salvar_titular(s: Session, dados: dict[str, Any], titular_id: int | None = None) -> Titular:
    documento = apenas_digitos(dados.get("documento"))
    if not valido(documento):
        raise ErroDeUso("CPF ou CNPJ inválido. Confira os números digitados.")
    nome = (dados.get("nome") or "").strip()
    if not nome:
        raise ErroDeUso("Informe o nome do titular.")

    duplicado = s.scalar(
        select(Titular).where(Titular.documento == documento, Titular.id != (titular_id or 0))
    )
    if duplicado:
        raise ErroDeUso(f"Já existe um titular cadastrado com o documento {formatar(documento)}.")

    titular = s.get(Titular, titular_id) if titular_id else Titular()
    if titular is None:
        raise ErroDeUso("Titular não encontrado.")

    titular.nome = nome
    titular.documento = documento
    titular.tipo = TipoPessoa(tipo_pessoa(documento))
    titular.inscricao_estadual = (dados.get("inscricao_estadual") or "").strip() or None
    titular.uf = (dados.get("uf") or "").strip().upper()[:2] or None
    titular.municipio = (dados.get("municipio") or "").strip() or None
    titular.codigo_ibge = (dados.get("codigo_ibge") or "").strip() or None
    titular.email = (dados.get("email") or "").strip() or None
    titular.observacoes = (dados.get("observacoes") or "").strip() or None
    if "ativo" in dados:
        titular.ativo = bool(dados["ativo"])
    if titular_id is None:
        s.add(titular)
    s.flush()
    registrar_evento(s, "titular", titular.id, "salvo", f"Titular {titular.nome} salvo.")
    return titular


def tipos_aplicaveis(s: Session, titular: Titular) -> list[TipoCertidao]:
    campo = TipoCertidao.aplica_pf if titular.tipo is TipoPessoa.PF else TipoCertidao.aplica_pj
    return list(s.scalars(select(TipoCertidao).where(TipoCertidao.ativo, campo).order_by(TipoCertidao.esfera, TipoCertidao.nome)))


def definir_monitoramentos(s: Session, titular_id: int, tipos_ids: Iterable[int],
                           dias_antecedencia: int = 15, renovar: bool = True) -> None:
    """Define exatamente quais certidões esse titular precisa manter vigentes."""
    desejados = set(tipos_ids)
    atuais = {m.tipo_certidao_id: m for m in s.scalars(
        select(Monitoramento).where(Monitoramento.titular_id == titular_id)
    )}
    for tipo_id in desejados - atuais.keys():
        s.add(Monitoramento(
            titular_id=titular_id, tipo_certidao_id=tipo_id,
            dias_antecedencia=dias_antecedencia, renovar_automaticamente=renovar,
        ))
    for tipo_id, monitoramento in atuais.items():
        monitoramento.ativo = tipo_id in desejados


# --------------------------------------------------------------------------- #
# Painel
# --------------------------------------------------------------------------- #

def certidao_vigente(s: Session, titular_id: int, tipo_id: int) -> Certidao | None:
    """A certidão mais recente e não substituída do par titular/tipo."""
    return s.scalar(
        select(Certidao)
        .where(
            Certidao.titular_id == titular_id,
            Certidao.tipo_certidao_id == tipo_id,
            Certidao.substituida.is_(False),
        )
        .order_by(Certidao.valida_ate.desc(), Certidao.id.desc())
        .limit(1)
    )


def solicitacao_em_andamento(s: Session, titular_id: int, tipo_id: int) -> Solicitacao | None:
    return s.scalar(
        select(Solicitacao)
        .where(
            Solicitacao.titular_id == titular_id,
            Solicitacao.tipo_certidao_id == tipo_id,
            Solicitacao.estado.in_([
                EstadoSolicitacao.NA_FILA,
                EstadoSolicitacao.EXECUTANDO,
                EstadoSolicitacao.AGUARDANDO_HUMANO,
                EstadoSolicitacao.AGUARDANDO_ANEXO,
            ]),
        )
        .order_by(Solicitacao.id.desc())
        .limit(1)
    )


def linha_do_painel(s: Session, monitoramento: Monitoramento, hoje: date | None = None) -> dict:
    certidao = certidao_vigente(s, monitoramento.titular_id, monitoramento.tipo_certidao_id)
    vigencia = avaliar(
        certidao.valida_ate if certidao else None,
        hoje=hoje,
        dias_antecedencia=monitoramento.dias_antecedencia,
        regular=certidao.situacao.regular if certidao else True,
    )
    andamento = solicitacao_em_andamento(s, monitoramento.titular_id, monitoramento.tipo_certidao_id)
    tipo = monitoramento.tipo
    titular = monitoramento.titular
    return {
        "monitoramento_id": monitoramento.id,
        "titular_id": titular.id,
        "titular": titular.nome,
        "documento": formatar(titular.documento),
        "tipo_id": tipo.id,
        "tipo": tipo.nome,
        "sigla": tipo.sigla or tipo.codigo.upper(),
        "orgao": tipo.orgao,
        "esfera": tipo.esfera.value,
        "modo": tipo.modo.value,
        "captcha": tipo.captcha.value,
        "requer_gov_br": tipo.requer_gov_br,
        "status": vigencia.status.value,
        "status_rotulo": vigencia.status.rotulo,
        "prioridade": vigencia.status.prioridade,
        "dias_restantes": vigencia.dias_restantes,
        "valida_ate": certidao.valida_ate.isoformat() if certidao else None,
        "emitida_em": certidao.emitida_em.isoformat() if certidao else None,
        "situacao": certidao.situacao.value if certidao else None,
        "certidao_id": certidao.id if certidao else None,
        "tem_arquivo": bool(certidao and certidao.arquivo),
        "renovar_automaticamente": monitoramento.renovar_automaticamente,
        "solicitacao_em_andamento": andamento.id if andamento else None,
        "estado_solicitacao": andamento.estado.value if andamento else None,
    }


def painel(s: Session, hoje: date | None = None, titular_id: int | None = None) -> list[dict]:
    consulta = (
        select(Monitoramento)
        .join(Titular)
        .where(Monitoramento.ativo, Titular.ativo)
        .order_by(Titular.nome)
    )
    if titular_id:
        consulta = consulta.where(Monitoramento.titular_id == titular_id)
    linhas = [linha_do_painel(s, m, hoje) for m in s.scalars(consulta)]
    linhas.sort(key=lambda l: (l["prioridade"], l["dias_restantes"] if l["dias_restantes"] is not None else 0))
    return linhas


def resumo(s: Session, hoje: date | None = None) -> dict:
    linhas = painel(s, hoje)
    contagem = {status.value: 0 for status in Status}
    for linha in linhas:
        contagem[linha["status"]] += 1
    return {
        "total": len(linhas),
        "por_status": contagem,
        "titulares": s.scalar(select(func.count(Titular.id)).where(Titular.ativo)) or 0,
        "pendencias": sum(
            contagem[s_.value] for s_ in (Status.VENCIDA, Status.AUSENTE, Status.VENCE_EM_BREVE, Status.IRREGULAR)
        ),
        "aguardando_humano": s.scalar(
            select(func.count(Desafio.id)).where(Desafio.estado == EstadoDesafio.ABERTO)
        ) or 0,
    }


# --------------------------------------------------------------------------- #
# Solicitações
# --------------------------------------------------------------------------- #

def solicitar(s: Session, titular_id: int, tipo_id: int, origem: str = "manual") -> Solicitacao:
    titular = s.get(Titular, titular_id)
    tipo = s.get(TipoCertidao, tipo_id)
    if titular is None or tipo is None:
        raise ErroDeUso("Titular ou tipo de certidão não encontrado.")

    if existente := solicitacao_em_andamento(s, titular_id, tipo_id):
        return existente

    solicitacao = Solicitacao(
        titular_id=titular_id, tipo_certidao_id=tipo_id, origem=origem, registro=[]
    )
    s.add(solicitacao)
    s.flush()
    registrar_evento(
        s, "solicitacao", solicitacao.id, "criada",
        f"{tipo.nome} para {titular.nome} entrou na fila ({origem}).",
    )
    return solicitacao


def variaveis_do_contexto(titular: Titular, tipo: TipoCertidao) -> dict[str, str]:
    return {
        "url": tipo.url or "",
        "url_tribunal": tipo.url or "",
        "documento": titular.documento,
        "documento_formatado": formatar(titular.documento),
        "cpf": titular.documento if titular.tipo is TipoPessoa.PF else "",
        "cnpj": titular.documento if titular.tipo is TipoPessoa.PJ else "",
        "nome": titular.nome,
        "email": titular.email or "",
        "uf": titular.uf or "",
        "municipio": titular.municipio or "",
        "codigo_ibge": titular.codigo_ibge or "",
        "inscricao_estadual": titular.inscricao_estadual or "",
        "fgts_tipo_inscricao": "1" if titular.tipo is TipoPessoa.PJ else "3",
    }


def guardar_resultado(
    s: Session,
    solicitacao: Solicitacao,
    *,
    documento: bytes,
    emitida_em: date | None,
    valida_ate: date | None,
    numero: str | None = None,
    codigo_verificacao: str | None = None,
    situacao: SituacaoCertidao = SituacaoCertidao.NAO_IDENTIFICADA,
    origem: str = "automacao",
) -> Certidao:
    """Arquiva o PDF e cria a certidão, marcando a anterior como substituída."""
    titular = s.get(Titular, solicitacao.titular_id)
    tipo = s.get(TipoCertidao, solicitacao.tipo_certidao_id)
    emissao = emitida_em or date.today()
    validade = valida_ate or calcular_validade(emissao, tipo.validade_dias)

    nome_arquivo = nomeacao.aplicar(
        preferencia(s, "padrao_nome_arquivo", nomeacao.PADRAO),
        nomeacao.campos(
            sigla=tipo.sigla or tipo.codigo.upper(), codigo=tipo.codigo, certidao=tipo.nome,
            orgao=tipo.orgao, nome=titular.nome, documento=titular.documento,
            documento_formatado=formatar(titular.documento),
            emitida_em=emissao, valida_ate=validade, numero=numero,
        ),
    )
    caminho, digest = arquivos.guardar(
        documento, documento=titular.documento, emitida_em=emissao, nome_arquivo=nome_arquivo
    )

    for anterior in s.scalars(
        select(Certidao).where(
            Certidao.titular_id == titular.id,
            Certidao.tipo_certidao_id == tipo.id,
            Certidao.substituida.is_(False),
        )
    ):
        anterior.substituida = True

    certidao = Certidao(
        titular_id=titular.id,
        tipo_certidao_id=tipo.id,
        numero=numero,
        codigo_verificacao=codigo_verificacao,
        emitida_em=emissao,
        valida_ate=validade,
        situacao=situacao,
        arquivo=caminho,
        arquivo_hash=digest,
        origem=origem,
        solicitacao_id=solicitacao.id,
    )
    s.add(certidao)
    s.flush()
    solicitacao.certidao_id = certidao.id
    registrar_evento(
        s, "certidao", certidao.id, "arquivada",
        f"{tipo.nome} de {titular.nome} válida até {validade.strftime('%d/%m/%Y')}.",
    )
    return certidao


def anexar_documento(s: Session, solicitacao_id: int, dados: bytes,
                     emitida_em: date | None = None, valida_ate: date | None = None) -> Certidao:
    """Recebe o PDF que o usuário baixou à mão e fecha a solicitação."""
    solicitacao = s.get(Solicitacao, solicitacao_id)
    if solicitacao is None:
        raise ErroDeUso("Solicitação não encontrada.")
    if not dados:
        raise ErroDeUso("O arquivo enviado está vazio.")

    lido = analisar(dados)
    certidao = guardar_resultado(
        s, solicitacao,
        documento=dados,
        emitida_em=emitida_em or lido["emitida_em"],
        valida_ate=valida_ate or lido["valida_ate"],
        numero=lido["numero"],
        codigo_verificacao=lido["codigo_verificacao"],
        situacao=lido["situacao"],
        origem="upload",
    )
    solicitacao.estado = EstadoSolicitacao.CONCLUIDA
    solicitacao.concluida_em = agora()
    solicitacao.mensagem = "Documento anexado pelo usuário."
    return certidao


def anotar(s: Session, solicitacao: Solicitacao, tipo: str, mensagem: str) -> None:
    registro = list(solicitacao.registro or [])
    registro.append({"em": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "tipo": tipo, "mensagem": mensagem})
    solicitacao.registro = registro[-200:]
