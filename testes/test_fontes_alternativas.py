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
