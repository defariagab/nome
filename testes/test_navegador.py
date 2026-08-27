"""Integração do motor de navegador contra uma réplica local de portal.

Não depende dos sites dos órgãos: valida o mecanismo (preencher, ler o
captcha, receber a recusa, repetir e baixar o PDF), que é o que costuma
quebrar. Pula automaticamente se o navegador do Playwright não estiver
instalado.
"""

from __future__ import annotations

import asyncio

import pytest

from certidoes.automacao.motor import executar
from certidoes.automacao.tipos import Contexto, Passo, Receita
from certidoes.modelos import SituacaoCertidao
from testes.site_falso import SiteFalso

pytestmark = pytest.mark.integracao


def _navegador_disponivel() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    from certidoes.config import config

    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch(
                headless=True,
                **({"executable_path": config.caminho_navegador} if config.caminho_navegador else {}),
            )
            navegador.close()
        return True
    except Exception:
        return False


def _contexto(url: str, respostas: list[str], captcha_de) -> Contexto:
    """Faz o papel da pessoa que responde ao captcha na tela."""

    async def perguntar(*, tipo, instrucao, imagem=None, timeout=300):
        return respostas.pop(0) if respostas else captcha_de()

    return Contexto(
        solicitacao_id=0,
        variaveis={"url": url, "documento": "11222333000181",
                   "documento_formatado": "11.222.333/0001-81", "uf": "SP"},
        perguntar=perguntar,
        registrar=lambda t, m: None,
        visivel=False,
    )


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_preenche_resolve_captcha_e_baixa_o_pdf():
    from testes import site_falso

    receita = Receita(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[
            Passo("abrir", {"url": "{url}"}),
            Passo("preencher", {"seletor": "#doc", "valor": "{documento_formatado}"}),
            Passo("captcha_imagem", {"seletor": "#cap", "campo": "#resp"}),
            Passo("clicar", {"seletor": "#ok"}),
            Passo("aguardar_download", {"timeout": 30, "falhar_se_texto": [
                {"texto": "nao conferem", "mensagem": "Captcha incorreto.", "repetir": True},
            ]}),
        ],
    )
    with SiteFalso() as site:
        contexto = _contexto(site.url, [], lambda: site_falso.RESPOSTA_CAPTCHA["valor"])
        resultado = asyncio.run(executar(receita, contexto, motor="navegador"))

    assert resultado.sucesso
    assert resultado.documento.startswith(b"%PDF")
    assert resultado.numero == "4242/2026"
    assert resultado.valida_ate.isoformat() == "2027-02-22"
    assert resultado.situacao is SituacaoCertidao.NEGATIVA


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_captcha_errado_e_repetido_ate_acertar():
    from testes import site_falso

    receita = Receita(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[
            Passo("abrir", {"url": "{url}"}),
            Passo("preencher", {"seletor": "#doc", "valor": "{documento}"}),
            Passo("captcha_imagem", {"seletor": "#cap", "campo": "#resp"}),
            Passo("clicar", {"seletor": "#ok"}),
            Passo("aguardar_download", {"timeout": 15, "falhar_se_texto": [
                {"texto": "nao conferem", "mensagem": "Captcha incorreto.", "repetir": True},
            ]}),
        ],
    )
    with SiteFalso() as site:
        contexto = _contexto(site.url, ["errado"], lambda: site_falso.RESPOSTA_CAPTCHA["valor"])
        resultado = asyncio.run(executar(receita, contexto, motor="navegador"))

    assert resultado.sucesso  # errou uma vez e o sistema refez sozinho


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_pagina_de_resultado_vira_pdf():
    receita = Receita(
        codigo="crf", nome="Certificado de teste", url="{url}/crf", resultado="pagina_pdf",
        passos=[
            Passo("abrir", {"url": "{url}/crf"}),
            Passo("preencher", {"seletor": "#ins", "valor": "{documento}"}),
            Passo("selecionar", {"seletor": "#uf", "valor": "{uf}"}),
            Passo("clicar", {"seletor": "#consultar"}),
            Passo("esperar", {"ms": 500}),
            Passo("exigir_texto", {"alternativas": ["Regularidade"],
                                   "mensagem": "O site não apresentou o certificado."}),
            Passo("salvar_pagina_pdf", {}),
        ],
    )
    with SiteFalso() as site:
        resultado = asyncio.run(executar(receita, _contexto(site.url, [], lambda: ""), motor="navegador"))

    assert resultado.documento.startswith(b"%PDF")
    assert resultado.valida_ate.isoformat() == "2026-09-26"
