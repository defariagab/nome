"""Integração do motor de navegador contra uma réplica local de portal.

Não depende dos sites dos órgãos: valida o mecanismo (preencher, ler o
captcha, receber a recusa, repetir e baixar o PDF), que é o que costuma
quebrar. Pula automaticamente se o navegador do Playwright não estiver
instalado.
"""

from __future__ import annotations

import asyncio
import base64

import pytest

from certidoes.automacao.motor import executar  # noqa: F401
from certidoes.automacao.tipos import Contexto, ErroAutomacao, Fonte, Passo
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


def _contexto(url: str, respostas: list[str], captcha_de, imagens: list | None = None) -> Contexto:
    """Faz o papel da pessoa que responde ao captcha na tela."""

    async def perguntar(*, tipo, instrucao, imagem=None, timeout=300):
        if imagens is not None and imagem:
            imagens.append(imagem)
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

    fonte = Fonte(
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
    imagens = []
    with SiteFalso() as site:
        contexto = _contexto(site.url, [], lambda: site_falso.RESPOSTA_CAPTCHA["valor"], imagens)
        resultado = asyncio.run(executar(fonte, contexto, motor="navegador"))

    # A imagem chega à tela por JavaScript, depois do elemento existir: se a
    # foto for tirada cedo demais, a pessoa recebe um captcha em branco.
    assert imagens, "nenhuma imagem de captcha foi apresentada"
    dados_da_imagem = base64.b64decode(imagens[0].split(",", 1)[1])
    assert len(dados_da_imagem) > 1000, "a imagem do captcha veio em branco"

    assert resultado.sucesso
    assert resultado.documento.startswith(b"%PDF")
    assert resultado.numero == "4242/2026"
    assert resultado.valida_ate.isoformat() == "2027-02-22"
    assert resultado.situacao is SituacaoCertidao.NEGATIVA


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_captcha_errado_e_repetido_ate_acertar():
    from testes import site_falso

    fonte = Fonte(
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
        resultado = asyncio.run(executar(fonte, contexto, motor="navegador"))

    assert resultado.sucesso  # errou uma vez e o sistema refez sozinho


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_pagina_de_resultado_vira_pdf():
    fonte = Fonte(
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
        resultado = asyncio.run(executar(fonte, _contexto(site.url, [], lambda: ""), motor="navegador"))

    assert resultado.documento.startswith(b"%PDF")
    assert resultado.valida_ate.isoformat() == "2026-09-26"


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_site_mudou_o_sistema_pede_o_anexo_em_vez_de_falhar():
    """Fonte desatualizada não pode virar beco sem saída para o usuário."""
    fonte = Fonte(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        ao_falhar="pedir_anexo",
        passos=[
            Passo("abrir", {"url": "{url}"}),
            Passo("preencher", {"seletor": "#campo-que-nao-existe", "valor": "{documento}"}),
            Passo("aguardar_download", {"timeout": 10}),
        ],
    )
    pedidos = []

    async def perguntar(*, tipo, instrucao, imagem=None, timeout=300):
        pedidos.append(tipo)
        return "ok"

    with SiteFalso() as site:
        contexto = Contexto(
            solicitacao_id=0,
            variaveis={"url": site.url, "documento": "11222333000181"},
            perguntar=perguntar, registrar=lambda t, m: None, visivel=False,
        )
        resultado = asyncio.run(executar(fonte, contexto, motor="navegador"))

    assert resultado.aguarda_anexo
    assert resultado.sucesso
    assert pedidos and pedidos[0].value == "acao_manual"


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_pagina_de_indisponibilidade_nao_vira_certidao():
    """A Caixa responde 200 com uma página que parece certificado. Não é."""
    fonte = Fonte(
        codigo="crf", nome="Certificado de teste", url="{url}/crf", resultado="pagina_pdf",
        passos=[
            Passo("abrir", {"url": "{url}/crf"}),
            Passo("preencher", {"seletor": "#ins", "valor": "{documento}"}),
            Passo("selecionar", {"seletor": "#uf", "valor": "{uf}"}),
            Passo("clicar", {"seletor": "#consultar"}),
            Passo("esperar", {"ms": 400}),
            Passo("exigir_texto", {"alternativas": ["certificado de regularidade", "CRF"]}),
            Passo("salvar_pagina_pdf", {}),
        ],
    )
    with SiteFalso() as site:
        contexto = _contexto(site.url, [], lambda: "")
        contexto.variaveis["documento"] = "00000000000000"  # dispara a resposta de erro
        with pytest.raises(ErroAutomacao, match="aviso"):
            asyncio.run(executar(fonte, contexto, motor="navegador"))


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_download_em_aba_nova_tambem_e_capturado():
    """Vários órgãos entregam o arquivo numa janela nova — ele não pode se perder."""
    fonte = Fonte(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[
            Passo("abrir", {"url": "{url}"}),
            Passo("clicar", {"seletor": "#ok-popup"}),
            Passo("aguardar_download", {"timeout": 20}),
        ],
    )
    with SiteFalso() as site:
        resultado = asyncio.run(executar(fonte, _contexto(site.url, [], lambda: ""), motor="navegador"))

    assert resultado.sucesso
    assert resultado.numero == "7777/2026"


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_emissoes_simultaneas_dividem_o_mesmo_navegador():
    """Uma janela, várias abas: quatro janelas escondem a sala de captchas."""
    from certidoes.automacao.motor_navegador import Navegador

    fonte = Fonte(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[
            Passo("abrir", {"url": "{url}"}),
            Passo("preencher", {"seletor": "#doc", "valor": "{documento}"}),
            Passo("captcha_imagem", {"seletor": "#cap", "campo": "#resp"}),
            Passo("clicar", {"seletor": "#ok"}),
            Passo("aguardar_download", {"timeout": 30, "falhar_se_texto": [
                {"texto": "nao conferem", "mensagem": "Captcha incorreto.", "repetir": True},
            ]}),
        ],
    )

    async def cenario():
        from testes import site_falso

        with SiteFalso() as site:
            async with Navegador(visivel=False) as navegador:
                contextos = [
                    _contexto(site.url, [], lambda: site_falso.RESPOSTA_CAPTCHA["valor"])
                    for _ in range(2)
                ]
                resultados = await asyncio.gather(*[
                    executar(fonte, c, motor="navegador", navegador=navegador) for c in contextos
                ])
                abas = len(navegador._contexto.pages)
                return resultados, abas

    resultados, abas = asyncio.run(cenario())
    assert all(r.sucesso for r in resultados)
    assert abas >= 2, "cada emissão deve ter a própria aba dentro do mesmo navegador"
