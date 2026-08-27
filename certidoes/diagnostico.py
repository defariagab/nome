"""Conferência das receitas contra os sites de verdade.

Sites de órgão mudam sem aviso. Esta conferência percorre a receita no site
real e diz até onde ela ainda funciona — **sem emitir nada**: ela para antes
do passo que geraria o documento e antes de pedir qualquer captcha.

Quando um campo não é encontrado, o relatório traz a lista de campos que a
página realmente tem, com o seletor de cada um. É o suficiente para consertar
a receita sem precisar abrir o site de novo.
"""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .automacao.inspecao import _EXTRAIR, _classificar
from .automacao.motor_navegador import Navegador
from .automacao.receitas import listar_receitas
from .automacao.tipos import Contexto, Receita
from .config import config

#: passos que produzem o documento — a conferência para antes deles
ACOES_DOCUMENTO = {"aguardar_download", "salvar_pagina_pdf"}
#: passos que exigem uma pessoa — a conferência confere e para
ACOES_PESSOA = {"captcha_imagem", "captcha_interativo", "login_gov_br", "acao_manual"}
#: passos que apenas navegam pela página
ACOES_NAVEGACAO = {"abrir", "esperar", "preencher", "selecionar", "clicar"}
ACOES_CONFERENCIA = {"exigir_texto"}

ACOES_CONHECIDAS = ACOES_DOCUMENTO | ACOES_PESSOA | ACOES_NAVEGACAO | ACOES_CONFERENCIA

OK = "ok"
NAO_ENCONTRADO = "nao_encontrado"
PULADO = "pulado"
ERRO = "erro"


@dataclass
class PassoConferido:
    acao: str
    seletor: str = ""
    resultado: str = OK
    detalhe: str = ""


@dataclass
class Conferencia:
    codigo: str
    nome: str
    url: str
    verificado_em: str | None = None
    situacao: str = "pronta"          # pronta | parcial | quebrada
    mensagem: str = ""
    passos: list[PassoConferido] = field(default_factory=list)
    #: campos que a página realmente tem, anexados quando algo não é achado
    campos_da_pagina: list[dict] = field(default_factory=list)
    captura: str = ""                 # imagem da tela no momento da falha

    def registrar(self, passo: PassoConferido) -> None:
        self.passos.append(passo)
        if passo.resultado in {NAO_ENCONTRADO, ERRO}:
            self.situacao = "quebrada"


async def _campos_da_pagina(pagina) -> list[dict]:
    try:
        campos = await pagina.evaluate(_EXTRAIR)
    except Exception:
        return []
    for campo in campos:
        campo["sugestao"] = _classificar(campo)
    return campos


async def _captura(pagina) -> str:
    try:
        imagem = await pagina.screenshot(full_page=False)
        return "data:image/png;base64," + base64.b64encode(imagem).decode()
    except Exception:
        return ""


async def _existe(pagina, seletor: str, espera: int = 8000) -> bool:
    try:
        await pagina.wait_for_selector(seletor, timeout=espera)
        return True
    except Exception:
        return False


async def conferir(receita: Receita, ctx: Contexto, visivel: bool = False) -> Conferencia:
    """Percorre a receita no site real, sem emitir. Devolve o que encontrou."""
    resultado = Conferencia(
        codigo=receita.codigo,
        nome=receita.nome,
        url=ctx.aplicar(receita.url),
        verificado_em=str(receita.verificado_em) if receita.verificado_em else None,
    )

    async with Navegador(visivel=visivel) as navegador:
        pagina = await navegador.nova_pagina()

        for indice, passo in enumerate(receita.passos):
            acao = passo.acao
            seguinte = receita.passos[indice + 1].acao if indice + 1 < len(receita.passos) else ""
            seletor = ctx.aplicar(passo.get("seletor"))

            if acao not in ACOES_CONHECIDAS:
                resultado.registrar(PassoConferido(acao, resultado=ERRO, detalhe="Passo desconhecido."))
                break

            if acao in ACOES_DOCUMENTO:
                resultado.registrar(PassoConferido(
                    acao, resultado=PULADO,
                    detalhe="A conferência para aqui para não emitir uma certidão de verdade.",
                ))
                break

            if acao in ACOES_PESSOA:
                achou = True
                if seletor:
                    achou = await _existe(pagina, seletor)
                campo = ctx.aplicar(passo.get("campo"))
                if achou and campo:
                    achou = await _existe(pagina, campo, espera=3000)
                resultado.registrar(PassoConferido(
                    acao, seletor or campo,
                    resultado=OK if achou else NAO_ENCONTRADO,
                    detalhe=("O ponto em que o sistema pede ajuda a uma pessoa foi encontrado."
                             if achou else "O captcha/campo esperado não está nesta página."),
                ))
                break

            try:
                if acao == "abrir":
                    endereco = ctx.aplicar(passo.get("url")) or receita.url
                    await pagina.goto(endereco, wait_until="domcontentloaded")
                    resultado.registrar(PassoConferido(acao, endereco))

                elif acao == "esperar":
                    if seletor:
                        achou = await _existe(pagina, seletor)
                        resultado.registrar(PassoConferido(
                            acao, seletor, OK if achou else NAO_ENCONTRADO,
                            "" if achou else "A página não apresentou este elemento.",
                        ))
                    else:
                        await pagina.wait_for_timeout(int(passo.get("ms", 1000)))
                        resultado.registrar(PassoConferido(acao, detalhe=f"{passo.get('ms', 1000)} ms"))

                elif acao in {"preencher", "selecionar"}:
                    if not await _existe(pagina, seletor):
                        resultado.registrar(PassoConferido(
                            acao, seletor, NAO_ENCONTRADO, "Campo não encontrado na página."))
                        break
                    if acao == "preencher":
                        await pagina.fill(seletor, ctx.aplicar(passo.get("valor")))
                    else:
                        await pagina.select_option(seletor, ctx.aplicar(passo.get("valor")))
                    resultado.registrar(PassoConferido(acao, seletor))

                elif acao == "clicar":
                    if seguinte in ACOES_DOCUMENTO:
                        achou = await _existe(pagina, seletor)
                        resultado.registrar(PassoConferido(
                            acao, seletor, OK if achou else NAO_ENCONTRADO,
                            "Botão de emissão encontrado; não foi clicado para não emitir."
                            if achou else "O botão de emissão não foi encontrado.",
                        ))
                        break
                    if not await _existe(pagina, seletor):
                        resultado.registrar(PassoConferido(
                            acao, seletor, NAO_ENCONTRADO, "Botão/link não encontrado."))
                        break
                    await pagina.click(seletor)
                    resultado.registrar(PassoConferido(acao, seletor))

                elif acao == "exigir_texto":
                    texto = (await pagina.inner_text("body")).lower()
                    alternativas = [str(a).lower() for a in (passo.get("alternativas") or [])]
                    achou = any(a in texto for a in alternativas)
                    resultado.registrar(PassoConferido(
                        acao, ", ".join(alternativas), OK if achou else NAO_ENCONTRADO,
                        "" if achou else "O texto esperado não apareceu (pode ser normal nesta etapa).",
                    ))

            except Exception as erro:
                resultado.registrar(PassoConferido(
                    acao, seletor, ERRO, f"{type(erro).__name__}: {str(erro).splitlines()[0][:160]}"
                ))
                break

        if resultado.situacao == "quebrada":
            resultado.campos_da_pagina = await _campos_da_pagina(pagina)
            resultado.captura = await _captura(pagina)

    resultado.mensagem = _resumir(resultado)
    return resultado


def _resumir(conferencia: Conferencia) -> str:
    if conferencia.situacao == "quebrada":
        falhou = next((p for p in conferencia.passos if p.resultado in {NAO_ENCONTRADO, ERRO}), None)
        onde = f" no passo '{falhou.acao}'" if falhou else ""
        return (f"A receita não corresponde mais ao site{onde}. O relatório traz os campos que a "
                "página tem hoje, com o seletor de cada um, para corrigir a receita.")
    ultimo = conferencia.passos[-1].acao if conferencia.passos else ""
    if ultimo in ACOES_PESSOA:
        return "Caminho conferido até o ponto em que uma pessoa precisa agir. A receita está de pé."
    return "Caminho conferido até o botão de emissão. A receita está de pé."


def _variaveis_de_teste() -> dict[str, str]:
    """Dados neutros para a conferência: nada de cliente real no relatório."""
    return {
        "url": "", "url_tribunal": "",
        "documento": "11222333000181", "documento_formatado": "11.222.333/0001-81",
        "cpf": "", "cnpj": "11222333000181",
        "nome": "Empresa de Teste", "email": "", "uf": "SP", "municipio": "São Paulo",
        "codigo_ibge": "", "inscricao_estadual": "", "fgts_tipo_inscricao": "1",
    }


async def conferir_todas(codigos: list[str] | None = None, visivel: bool = False) -> dict:
    """Confere as receitas pedidas (ou todas) e monta o relatório."""
    conferencias = []
    for receita in listar_receitas():
        if codigos and receita.codigo not in codigos:
            continue

        async def sem_perguntar(**_kwargs):  # a conferência nunca pede ajuda
            return ""

        variaveis = _variaveis_de_teste()
        variaveis["url"] = receita.url
        variaveis["url_tribunal"] = receita.url
        ctx = Contexto(
            solicitacao_id=0, variaveis=variaveis, perguntar=sem_perguntar,
            registrar=lambda t, m: None, visivel=visivel,
        )
        try:
            conferencias.append(await conferir(receita, ctx, visivel=visivel))
        except Exception as erro:
            conferencias.append(Conferencia(
                codigo=receita.codigo, nome=receita.nome, url=receita.url,
                situacao="quebrada",
                mensagem=f"Não consegui abrir o site: {type(erro).__name__}: {str(erro).splitlines()[0][:160]}",
            ))

    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "versao": __import__("certidoes").__version__,
        "receitas": [asdict(c) for c in conferencias],
    }


def salvar_relatorio(relatorio: dict) -> Path:
    """Grava o relatório para o escritório enviar a quem for corrigir a receita."""
    pasta = config.pasta_dados / "diagnostico"
    pasta.mkdir(parents=True, exist_ok=True)
    momento = relatorio["gerado_em"].replace(":", "-")
    caminho = pasta / f"conferencia-{momento}.json"
    caminho.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    (pasta / f"conferencia-{momento}.md").write_text(em_texto(relatorio), encoding="utf-8")
    return caminho


def em_texto(relatorio: dict) -> str:
    """Versão legível do relatório, para colar num e-mail ou numa conversa."""
    linhas = [f"# Conferência das receitas — {relatorio['gerado_em']}", ""]
    for receita in relatorio["receitas"]:
        selo = {"pronta": "OK", "parcial": "ATENÇÃO", "quebrada": "PRECISA DE AJUSTE"}
        linhas.append(f"## {receita['nome']} [{selo.get(receita['situacao'], receita['situacao'])}]")
        linhas.append(f"- endereço: {receita['url']}")
        linhas.append(f"- {receita['mensagem']}")
        for passo in receita.get("passos", []):
            marca = {OK: "✓", PULADO: "–", NAO_ENCONTRADO: "✗", ERRO: "✗"}.get(passo["resultado"], "?")
            detalhe = f" — {passo['detalhe']}" if passo["detalhe"] else ""
            linhas.append(f"  {marca} {passo['acao']} {passo['seletor']}{detalhe}")
        if campos := receita.get("campos_da_pagina"):
            linhas.append("")
            linhas.append("  Campos que a página tem hoje:")
            for campo in campos[:40]:
                rotulo = campo.get("rotulo") or campo.get("texto") or campo.get("alternativo") or ""
                linhas.append(f"    {campo['sugestao']:22} {campo['seletor']:44} {rotulo[:40]}")
        linhas.append("")
    return "\n".join(linhas)
