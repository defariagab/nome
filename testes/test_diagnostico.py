"""A conferência das receitas: diz até onde a receita ainda funciona, sem emitir."""

from __future__ import annotations

import asyncio

import pytest

from certidoes import diagnostico
from certidoes.automacao.receitas import listar_receitas
from certidoes.automacao.tipos import Contexto, Passo, Receita
from testes.site_falso import SiteFalso
from testes.test_navegador import _navegador_disponivel

pytestmark = pytest.mark.integracao


def _contexto(url: str) -> Contexto:
    async def sem_perguntar(**_kwargs):
        return ""

    variaveis = diagnostico._variaveis_de_teste()
    variaveis["url"] = url
    return Contexto(
        solicitacao_id=0, variaveis=variaveis, perguntar=sem_perguntar,
        registrar=lambda t, m: None, visivel=False,
    )


def test_toda_acao_usada_nas_receitas_e_conhecida_pela_conferencia():
    """Guarda contra a conferência ficar para trás quando o motor ganha um passo."""
    for receita in listar_receitas():
        for passo in receita.passos:
            assert passo.acao in diagnostico.ACOES_CONHECIDAS, (
                f"{receita.codigo}: a conferência não sabe tratar o passo '{passo.acao}'"
            )


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_receita_boa_e_conferida_ate_o_captcha_sem_emitir():
    receita = Receita(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[
            Passo("abrir", {"url": "{url}"}),
            Passo("preencher", {"seletor": "#doc", "valor": "{documento_formatado}"}),
            Passo("captcha_imagem", {"seletor": "#cap", "campo": "#resp"}),
            Passo("clicar", {"seletor": "#ok"}),
            Passo("aguardar_download", {"timeout": 30}),
        ],
    )
    with SiteFalso() as site:
        conferencia = asyncio.run(diagnostico.conferir(receita, _contexto(site.url)))

    assert conferencia.situacao == "pronta"
    assert [p.acao for p in conferencia.passos] == ["abrir", "preencher", "captcha_imagem"]
    assert conferencia.passos[-1].resultado == diagnostico.OK
    assert "pessoa" in conferencia.mensagem


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_receita_desatualizada_traz_os_campos_reais_da_pagina():
    """É este relatório que permite consertar a receita sem abrir o site de novo."""
    receita = Receita(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[
            Passo("abrir", {"url": "{url}"}),
            Passo("preencher", {"seletor": "#campo-que-o-orgao-renomeou", "valor": "{documento}"}),
            Passo("aguardar_download", {"timeout": 10}),
        ],
    )
    with SiteFalso() as site:
        conferencia = asyncio.run(diagnostico.conferir(receita, _contexto(site.url)))

    assert conferencia.situacao == "quebrada"
    assert conferencia.passos[-1].resultado == diagnostico.NAO_ENCONTRADO
    seletores = {campo["seletor"] for campo in conferencia.campos_da_pagina}
    assert '[id="doc"]' in seletores          # o campo que a receita deveria usar
    assert conferencia.captura.startswith("data:image/png;base64,")
    assert "corrigir a receita" in conferencia.mensagem


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_conferencia_para_antes_de_gerar_o_pdf_da_pagina():
    receita = Receita(
        codigo="crf", nome="Certificado de teste", url="{url}/crf", resultado="pagina_pdf",
        passos=[
            Passo("abrir", {"url": "{url}/crf"}),
            Passo("preencher", {"seletor": "#ins", "valor": "{documento}"}),
            Passo("selecionar", {"seletor": "#uf", "valor": "{uf}"}),
            Passo("clicar", {"seletor": "#consultar"}),
            Passo("esperar", {"ms": 400}),
            Passo("exigir_texto", {"alternativas": ["Regularidade"]}),
            Passo("salvar_pagina_pdf", {}),
        ],
    )
    with SiteFalso() as site:
        conferencia = asyncio.run(diagnostico.conferir(receita, _contexto(site.url)))

    assert conferencia.situacao == "pronta"
    assert conferencia.passos[-1].acao == "salvar_pagina_pdf"
    assert conferencia.passos[-1].resultado == diagnostico.PULADO


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_relatorio_em_texto_e_legivel_e_nao_traz_dado_de_cliente():
    receita = Receita(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[Passo("abrir", {"url": "{url}"}), Passo("preencher", {"seletor": "#doc", "valor": "{documento}"})],
    )
    with SiteFalso() as site:
        conferencia = asyncio.run(diagnostico.conferir(receita, _contexto(site.url)))

    from dataclasses import asdict

    relatorio = {"gerado_em": "2026-08-27T12:00:00", "versao": "0.1.0",
                 "receitas": [asdict(conferencia)]}
    texto = diagnostico.em_texto(relatorio)
    assert "Certidão de teste" in texto
    assert "✓ abrir" in texto
    assert "11.222.333/0001-81" not in texto  # valores preenchidos não vão para o relatório

    caminho = diagnostico.salvar_relatorio(relatorio)
    assert caminho.exists()
    assert caminho.with_suffix(".md").exists()
