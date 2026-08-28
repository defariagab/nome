"""Emissão por API contratada.

Onde existe um serviço oficial — como a API Consulta CND do Serpro, que
consulta as certidões federais de RFB e PGFN — chamar a API é melhor do que
operar o site: não há captcha, não há bloqueio a automação, o contrato dá
suporte e a resposta não quebra quando o órgão muda o layout da página.

A chamada é declarada na própria fonte, o que permite ligar um fornecedor
novo sem tocar no código.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import date, datetime
from typing import Any

from ..modelos import SituacaoCertidao
from .extracao import analisar
from .tipos import Contexto, ErroAutomacao, Fonte, Resultado

TEMPO_LIMITE = 90.0


class CredencialAusente(ErroAutomacao):
    """A fonte precisa de um token que ainda não foi cadastrado."""


def _resolver(valor: Any, ctx: Contexto) -> Any:
    """Troca {variaveis} em textos, listas e dicionários da configuração."""
    if isinstance(valor, str):
        return ctx.aplicar(valor)
    if isinstance(valor, dict):
        return {chave: _resolver(item, ctx) for chave, item in valor.items()}
    if isinstance(valor, list):
        return [_resolver(item, ctx) for item in valor]
    return valor


def buscar(dados: Any, caminho: str) -> Any:
    """Lê um campo da resposta pelo caminho declarado, como `dados.certidao.pdf`.

    Aceita índice de lista (`itens.0.pdf`), porque as APIs variam no formato e
    a fonte precisa poder descrever o que veio sem exigir código novo.
    """
    atual = dados
    for parte in (caminho or "").split("."):
        if not parte:
            continue
        if isinstance(atual, list):
            try:
                atual = atual[int(parte)]
            except (ValueError, IndexError):
                return None
        elif isinstance(atual, dict):
            atual = atual.get(parte)
        else:
            return None
        if atual is None:
            return None
    return atual


def _data(valor: Any, formatos: list[str]) -> date | None:
    if isinstance(valor, date):
        return valor
    if not isinstance(valor, str) or not valor.strip():
        return None
    for formato in formatos + ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]:
        try:
            return datetime.strptime(valor.strip()[:10], formato).date()
        except ValueError:
            continue
    return None


def _documento(bruto: Any) -> bytes | None:
    """A certidão costuma vir em base64 dentro do JSON."""
    if isinstance(bruto, bytes):
        return bruto
    if not isinstance(bruto, str) or len(bruto) < 100:
        return None
    texto = bruto.split(",", 1)[-1].strip()  # tolera "data:application/pdf;base64,..."
    try:
        return base64.b64decode(texto, validate=False)
    except (binascii.Error, ValueError):
        return None


async def executar(fonte: Fonte, ctx: Contexto, token: str | None = None) -> Resultado:
    """Chama a API declarada na fonte e devolve a certidão."""
    import httpx

    config_api = fonte.api or {}
    endereco = ctx.aplicar(config_api.get("endereco") or fonte.url)
    if not endereco:
        raise ErroAutomacao("A fonte não declara o endereço da API.")

    if config_api.get("exige_token", True) and not token:
        raise CredencialAusente(
            f"Falta a credencial da API para esta certidão. Cadastre o token em "
            f"Configurações › Credenciais de API, com o rótulo "
            f'"{config_api.get("credencial", fonte.codigo)}".'
        )

    cabecalhos = {"Accept": "application/json"}
    cabecalhos.update(_resolver(config_api.get("cabecalhos", {}), ctx))
    if token:
        modelo = config_api.get("autorizacao", "Bearer {token}")
        cabecalhos["Authorization"] = modelo.replace("{token}", token)

    metodo = str(config_api.get("metodo", "GET")).upper()
    parametros = _resolver(config_api.get("parametros", {}), ctx)
    corpo = _resolver(config_api.get("corpo"), ctx)

    ctx.registrar("api", f"{metodo} {endereco}")
    try:
        async with httpx.AsyncClient(timeout=TEMPO_LIMITE, follow_redirects=True) as cliente:
            resposta = await cliente.request(
                metodo, endereco, headers=cabecalhos, params=parametros or None,
                json=corpo if corpo else None,
            )
    except Exception as erro:
        raise ErroAutomacao(
            f"Não consegui falar com a API ({type(erro).__name__}). "
            "Confira a conexão e o endereço do serviço."
        ) from erro

    if resposta.status_code in (401, 403):
        raise CredencialAusente(
            "A API recusou a credencial (a chamada voltou como não autorizada). "
            "Confira se o token está correto e se o contrato está ativo."
        )
    if resposta.status_code == 429:
        raise ErroAutomacao("A API pediu para esperar: limite de chamadas atingido no momento.")
    if resposta.status_code >= 400:
        detalhe = resposta.text[:200].replace("\n", " ")
        raise ErroAutomacao(f"A API respondeu com erro {resposta.status_code}: {detalhe}")

    # Algumas APIs devolvem o PDF direto; a maioria, um JSON com ele dentro.
    if resposta.headers.get("content-type", "").startswith("application/pdf"):
        return _montar(fonte, resposta.content, {}, config_api)

    try:
        dados = resposta.json()
    except (json.JSONDecodeError, ValueError) as erro:
        raise ErroAutomacao("A API respondeu num formato que não sei ler.") from erro

    mapa = config_api.get("resposta", {})
    if campo_erro := mapa.get("erro"):
        if mensagem := buscar(dados, campo_erro):
            raise ErroAutomacao(f"A API não emitiu a certidão: {mensagem}")

    documento = _documento(buscar(dados, mapa.get("documento", "")))
    if documento is None:
        raise ErroAutomacao(
            "A resposta da API não trouxe o arquivo da certidão. Confira o campo "
            f'"{mapa.get("documento", "(não configurado)")}" na configuração da fonte.'
        )
    return _montar(fonte, documento, dados, config_api)


def _montar(fonte: Fonte, documento: bytes, dados: dict, config_api: dict) -> Resultado:
    mapa = config_api.get("resposta", {})
    formatos = [f for f in [mapa.get("formato_de_data")] if f]
    lido = analisar(documento)

    situacao = lido["situacao"]
    if bruto := buscar(dados, mapa.get("situacao", "")):
        texto = str(bruto).lower()
        if "positiva com efeito" in texto or "efeitos de negativa" in texto:
            situacao = SituacaoCertidao.POSITIVA_COM_EFEITO_NEGATIVO
        elif "negativa" in texto:
            situacao = SituacaoCertidao.NEGATIVA
        elif "positiva" in texto:
            situacao = SituacaoCertidao.POSITIVA

    return Resultado(
        sucesso=True,
        documento=documento,
        numero=(buscar(dados, mapa.get("numero", "")) or lido["numero"]),
        codigo_verificacao=(buscar(dados, mapa.get("codigo", "")) or lido["codigo_verificacao"]),
        emitida_em=_data(buscar(dados, mapa.get("emissao", "")), formatos) or lido["emitida_em"] or date.today(),
        valida_ate=_data(buscar(dados, mapa.get("validade", "")), formatos) or lido["valida_ate"],
        situacao=situacao,
        texto_extraido=lido["texto"],
        custo=float(config_api.get("custo_por_emissao", 0) or 0),
        mensagem="Certidão emitida pela API contratada.",
    )
