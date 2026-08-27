"""A conferência das fontes: diz até onde a fonte ainda funciona, sem emitir."""

from __future__ import annotations

import asyncio

import pytest

from certidoes import diagnostico
from certidoes.automacao.fontes import listar_fontes
from certidoes.automacao.tipos import Contexto, Fonte, Passo
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


def test_toda_acao_usada_nas_fontes_e_conhecida_pela_conferencia():
    """Guarda contra a conferência ficar para trás quando o motor ganha um passo."""
    for fonte in listar_fontes():
        for passo in fonte.passos:
            assert passo.acao in diagnostico.ACOES_CONHECIDAS, (
                f"{fonte.codigo}: a conferência não sabe tratar o passo '{passo.acao}'"
            )


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_fonte_boa_e_conferida_ate_o_captcha_sem_emitir():
    fonte = Fonte(
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
        conferencia = asyncio.run(diagnostico.conferir(fonte, _contexto(site.url)))

    assert conferencia.situacao == "pronta"
    assert [p.acao for p in conferencia.passos] == ["abrir", "preencher", "captcha_imagem"]
    assert conferencia.passos[-1].resultado == diagnostico.OK
    assert "pessoa" in conferencia.mensagem


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_fonte_desatualizada_traz_os_campos_reais_da_pagina():
    """É este relatório que permite consertar a fonte sem abrir o site de novo."""
    fonte = Fonte(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[
            Passo("abrir", {"url": "{url}"}),
            Passo("preencher", {"seletor": "#campo-que-o-orgao-renomeou", "valor": "{documento}"}),
            Passo("aguardar_download", {"timeout": 10}),
        ],
    )
    with SiteFalso() as site:
        conferencia = asyncio.run(diagnostico.conferir(fonte, _contexto(site.url)))

    assert conferencia.situacao == "quebrada"
    assert conferencia.passos[-1].resultado == diagnostico.NAO_ENCONTRADO
    seletores = {campo["seletor"] for campo in conferencia.campos_da_pagina}
    assert '[id="doc"]' in seletores          # o campo que a fonte deveria usar
    assert conferencia.captura.startswith("data:image/png;base64,")
    assert "corrigir a fonte" in conferencia.mensagem


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_conferencia_para_antes_de_gerar_o_pdf_da_pagina():
    fonte = Fonte(
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
        conferencia = asyncio.run(diagnostico.conferir(fonte, _contexto(site.url)))

    assert conferencia.situacao == "pronta"
    assert conferencia.passos[-1].acao == "salvar_pagina_pdf"
    assert conferencia.passos[-1].resultado == diagnostico.PULADO


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_relatorio_em_texto_e_legivel_e_nao_traz_dado_de_cliente():
    fonte = Fonte(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[Passo("abrir", {"url": "{url}"}), Passo("preencher", {"seletor": "#doc", "valor": "{documento}"})],
    )
    with SiteFalso() as site:
        conferencia = asyncio.run(diagnostico.conferir(fonte, _contexto(site.url)))

    from dataclasses import asdict

    relatorio = {"gerado_em": "2026-08-27T12:00:00", "versao": "0.1.0",
                 "fontes": [asdict(conferencia)]}
    texto = diagnostico.em_texto(relatorio)
    assert "Certidão de teste" in texto
    assert "✓ abrir" in texto
    assert "11.222.333/0001-81" not in texto  # valores preenchidos não vão para o relatório

    caminho = diagnostico.salvar_relatorio(relatorio)
    assert caminho.exists()
    assert caminho.with_suffix(".md").exists()


def test_passo_que_nao_se_aplica_ao_titular_e_pulado():
    """CPF e CNPJ em campos separados: só o do titular deve ser exercitado."""
    from certidoes.automacao.tipos import Passo

    pj = {"cnpj": "11222333000181", "cpf": ""}
    assert Passo("preencher", {"quando": "cnpj"}).se_aplica(pj)
    assert not Passo("preencher", {"quando": "!cnpj"}).se_aplica(pj)

    pf = {"cnpj": "", "cpf": "52998224725"}
    assert not Passo("preencher", {"quando": "cnpj"}).se_aplica(pf)
    assert Passo("preencher", {"quando": "!cnpj"}).se_aplica(pf)


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_relatorio_avisa_quando_o_seletor_e_largo_demais():
    """Um seletor que casa com vários elementos pode preencher o campo errado."""
    fonte = Fonte(
        codigo="teste", nome="Certidão de teste", url="{url}", resultado="download",
        passos=[
            Passo("abrir", {"url": "{url}"}),
            Passo("preencher", {"seletor": "input[type='text']", "valor": "{documento}"}),
            Passo("aguardar_download", {"timeout": 5}),
        ],
    )
    with SiteFalso() as site:
        conferencia = asyncio.run(diagnostico.conferir(fonte, _contexto(site.url)))

    preencher = next(p for p in conferencia.passos if p.acao == "preencher")
    assert "casa com" in preencher.detalhe  # a página de teste tem dois campos de texto


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_relatorio_separa_campo_ausente_de_campo_escondido():
    """São problemas diferentes: um pede outro seletor, o outro pede um passo antes."""
    def conferir_seletor(seletor: str):
        fonte = Fonte(
            codigo="teste", nome="Teste", url="{url}", resultado="download",
            passos=[
                Passo("abrir", {"url": "{url}"}),
                Passo("preencher", {"seletor": seletor, "valor": "{documento}"}),
                Passo("aguardar_download", {"timeout": 5}),
            ],
        )
        with SiteFalso() as site:
            return asyncio.run(diagnostico.conferir(fonte, _contexto(site.url)))

    ausente = conferir_seletor("#campo-que-nunca-existiu")
    assert "não encontrado" in ausente.passos[-1].detalhe

    escondido = conferir_seletor("#escondido")
    assert "existe" in escondido.passos[-1].detalhe
    assert "input[type=text] #escondido" in escondido.passos[-1].detalhe
    assert "falta um passo antes" in escondido.passos[-1].detalhe


@pytest.mark.skipif(not _navegador_disponivel(), reason="navegador do Playwright indisponível")
def test_relatorio_mostra_a_etiqueta_e_o_tipo_de_cada_campo():
    """Sem o tipo, não dá para saber se [id=cnpj] é caixa de texto ou opção."""
    from dataclasses import asdict

    fonte = Fonte(
        codigo="teste", nome="Teste", url="{url}", resultado="download",
        passos=[Passo("abrir", {"url": "{url}"}),
                Passo("preencher", {"seletor": "#nao-existe", "valor": "x"})],
    )
    with SiteFalso() as site:
        conferencia = asyncio.run(diagnostico.conferir(fonte, _contexto(site.url)))

    texto = diagnostico.em_texto(
        {"gerado_em": "x", "versao": "0", "fontes": [asdict(conferencia)]}
    )
    assert "input[radio]" in texto     # a opção aparece como opção
    assert "input[text]" in texto      # e a caixa de texto, como caixa de texto


def test_fonte_que_so_abre_o_navegador_do_usuario_nao_abre_o_nosso():
    """O portal da Receita recusa navegador automatizado: não insistimos."""
    from certidoes.automacao.fontes import carregar_fonte

    rfb = carregar_fonte("rfb_pgfn_conjunta")
    assert not rfb.exige_navegador
    assert [p.acao for p in rfb.passos] == ["abrir_no_navegador", "acao_manual"]
