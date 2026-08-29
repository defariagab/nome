"""A mesma certidão por caminhos diferentes — a escolha é do escritório."""

import pytest
from sqlalchemy import select

from certidoes import servicos
from certidoes.fila import _fonte_para
from certidoes.modelos import TipoCertidao


def _tipo(s, codigo):
    return s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == codigo))


def test_cnd_federal_tem_site_e_api(s):
    fontes = servicos.fontes_do_tipo(_tipo(s, "rfb_pgfn_conjunta"))
    codigos = [f["codigo"] for f in fontes]
    assert codigos == ["rfb_pgfn_conjunta", "rfb_pgfn_api_serpro"]

    site, api = fontes
    assert site["padrao"] and site["tipo"] == "navegador"
    assert not api["padrao"] and api["tipo"] == "api"
    assert api["credencial"] == "serpro_cnd"


def test_certidao_com_uma_fonte_so_continua_simples(s):
    fontes = servicos.fontes_do_tipo(_tipo(s, "cndt"))
    assert [f["codigo"] for f in fontes] == ["cndt"]
    assert fontes[0]["padrao"]


def test_emissao_usa_a_fonte_escolhida(s, titular_exemplo):
    tipo = _tipo(s, "rfb_pgfn_conjunta")
    solicitacao = servicos.solicitar(s, titular_exemplo.id, tipo.id, fonte="rfb_pgfn_api_serpro")
    s.flush()

    assert solicitacao.fonte == "rfb_pgfn_api_serpro"
    assert _fonte_para(tipo, solicitacao.fonte).tipo == "api"
    assert _fonte_para(tipo, None).tipo == "navegador"   # sem escolha, a padrão


def test_fonte_de_outra_certidao_e_recusada(s, titular_exemplo):
    tipo = _tipo(s, "cndt")
    with pytest.raises(servicos.ErroDeUso, match="não está disponível"):
        servicos.solicitar(s, titular_exemplo.id, tipo.id, fonte="rfb_pgfn_api_serpro")


def test_emissao_por_api_pode_rodar_em_paralelo(s):
    """A API não disputa janela nem captcha: várias ao mesmo tempo."""
    from certidoes.automacao.fontes import carregar_fonte

    assert carregar_fonte("rfb_pgfn_api_serpro").paralelizavel
    assert not carregar_fonte("rfb_pgfn_api_serpro").exige_navegador


def test_certidoes_novas_do_catalogo(s):
    assert _tipo(s, "pf_antecedentes_criminais").aplica_pf
    assert not _tipo(s, "pf_antecedentes_criminais").aplica_pj
    ccir = _tipo(s, "incra_ccir")
    assert [f["codigo"] for f in servicos.fontes_do_tipo(ccir)] == [
        "incra_ccir_site", "incra_ccir_api_serpro"
    ]


def test_a_janela_do_navegador_so_aparece_quando_a_pessoa_precisa_dela():
    """Ver o site sendo preenchido não ajuda: atrapalha.

    A janela pulando na frente do painel foi reclamação do usuário — e é o
    oposto do que o sistema promete. Ela só se justifica onde o órgão exige a
    pessoa nele.
    """
    from certidoes.automacao.tipos import Fonte, Passo

    def fonte(*acoes, perfil=None, tipo="navegador"):
        return Fonte(codigo="x", nome="x", url="", perfil=perfil, tipo=tipo,
                     passos=[Passo(a, {}) for a in acoes])

    assert not fonte("abrir", "preencher", "captcha_imagem", "aguardar_download").exige_janela
    assert not fonte("abrir", "salvar_pagina_pdf").exige_janela
    assert fonte("abrir", "captcha_interativo").exige_janela
    assert fonte("abrir", "login_gov_br").exige_janela
    assert fonte("abrir", perfil="govbr").exige_janela
    assert not fonte(tipo="api").exige_janela


def test_fila_abre_janela_apenas_para_a_fonte_que_precisa(monkeypatch):
    from certidoes.automacao.tipos import Fonte, Passo
    from certidoes.config import config

    monkeypatch.setattr(config, "navegador_visivel", False)
    com_captcha_de_letras = Fonte(codigo="x", nome="x", url="",
                                  passos=[Passo("captcha_imagem", {})])
    com_login = Fonte(codigo="y", nome="y", url="", passos=[Passo("login_gov_br", {})])
    assert not (config.navegador_visivel or com_captcha_de_letras.exige_janela)
    assert config.navegador_visivel or com_login.exige_janela
