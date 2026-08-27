"""Excluir o que entrou errado, sem derrubar o resto."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from certidoes import arquivos, servicos
from certidoes.automacao.pdf_simples import gerar
from certidoes.modelos import Certidao, EstadoSolicitacao, SituacaoCertidao, Solicitacao, TipoCertidao


def _arquivar(s, titular, codigo, dias, conteudo="CERTIDAO NEGATIVA"):
    tipo = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == codigo))
    solicitacao = servicos.solicitar(s, titular.id, tipo.id)
    solicitacao.estado = EstadoSolicitacao.CONCLUIDA
    hoje = date.today()
    certidao = servicos.guardar_resultado(
        s, solicitacao, documento=gerar([conteudo], titulo=codigo),
        emitida_em=hoje, valida_ate=hoje + timedelta(days=dias),
        situacao=SituacaoCertidao.NEGATIVA,
    )
    s.flush()
    return certidao


def test_excluir_certidao_apaga_o_arquivo(s, titular_exemplo):
    certidao = _arquivar(s, titular_exemplo, "cndt", 100)
    caminho = arquivos.caminho_absoluto(certidao.arquivo)
    assert caminho.exists()

    servicos.excluir_certidao(s, certidao.id)
    assert not caminho.exists()
    assert s.get(Certidao, certidao.id) is None


def test_ao_excluir_a_atual_a_anterior_volta_a_valer(s, titular_exemplo):
    antiga = _arquivar(s, titular_exemplo, "cndt", 30, "CERTIDAO NEGATIVA antiga")
    nova = _arquivar(s, titular_exemplo, "cndt", 170, "CERTIDAO NEGATIVA nova")
    s.refresh(antiga)
    assert antiga.substituida

    servicos.excluir_certidao(s, nova.id)
    s.flush()
    vigente = servicos.certidao_vigente(s, titular_exemplo.id, antiga.tipo_certidao_id)
    assert vigente is not None and vigente.id == antiga.id


def test_excluir_solicitacao_nao_apaga_a_certidao(s, titular_exemplo):
    certidao = _arquivar(s, titular_exemplo, "cndt", 100)
    solicitacao_id = s.scalar(select(Solicitacao.id).where(Solicitacao.certidao_id == certidao.id))

    servicos.excluir_solicitacao(s, solicitacao_id)
    s.flush()
    assert s.get(Solicitacao, solicitacao_id) is None
    assert s.get(Certidao, certidao.id) is not None


def test_solicitacao_em_andamento_nao_e_excluida(s, titular_exemplo):
    cndt = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "cndt"))
    solicitacao = servicos.solicitar(s, titular_exemplo.id, cndt.id)
    s.flush()
    with pytest.raises(servicos.ErroDeUso, match="Cancele antes"):
        servicos.excluir_solicitacao(s, solicitacao.id)


def test_limpar_tira_o_que_terminou_e_deixa_o_resto(s, titular_exemplo):
    cndt = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "cndt"))
    fgts = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "fgts_crf"))

    falhou = servicos.solicitar(s, titular_exemplo.id, cndt.id)
    falhou.estado = EstadoSolicitacao.FALHOU
    na_fila = servicos.solicitar(s, titular_exemplo.id, fgts.id)
    s.flush()

    assert servicos.limpar_solicitacoes(s) == 1
    s.flush()
    assert s.get(Solicitacao, falhou.id) is None
    assert s.get(Solicitacao, na_fila.id) is not None


def test_excluir_titular_leva_tudo_junto(s, titular_exemplo):
    certidao = _arquivar(s, titular_exemplo, "cndt", 100)
    caminho = arquivos.caminho_absoluto(certidao.arquivo)
    cndt = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "cndt"))
    servicos.definir_monitoramentos(s, titular_exemplo.id, [cndt.id])
    s.flush()

    resumo = servicos.excluir_titular(s, titular_exemplo.id)
    s.flush()

    assert resumo["certidoes"] == 1
    assert not caminho.exists()
    assert s.get(Certidao, certidao.id) is None
    assert servicos.painel(s) == []


def test_titular_de_outro_nao_e_afetado(s, titular_exemplo):
    outro = servicos.salvar_titular(s, {"nome": "Outra Empresa", "documento": "34.028.316/0001-03"})
    s.flush()
    _arquivar(s, titular_exemplo, "cndt", 100)
    certidao_do_outro = _arquivar(s, outro, "cndt", 100)

    servicos.excluir_titular(s, titular_exemplo.id)
    s.flush()

    assert s.get(Certidao, certidao_do_outro.id) is not None
    assert arquivos.caminho_absoluto(certidao_do_outro.arquivo).exists()
