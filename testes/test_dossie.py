"""O dossiê de regularidade: um PDF só, com o que está vigente."""

from datetime import date, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from certidoes import servicos
from certidoes.automacao.pdf_simples import gerar
from certidoes.dossie import SemCertidoes, certidoes_do_dossie, montar
from certidoes.modelos import EstadoSolicitacao, SituacaoCertidao, TipoCertidao

import io


def _arquivar(s, titular, codigo, *, dias_para_vencer, situacao=SituacaoCertidao.NEGATIVA):
    tipo = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == codigo))
    solicitacao = servicos.solicitar(s, titular.id, tipo.id)
    solicitacao.estado = EstadoSolicitacao.CONCLUIDA
    hoje = date.today()
    pdf = gerar([f"{tipo.nome[:40]}", f"Titular: {titular.nome}", "CERTIDAO NEGATIVA"], titulo=codigo)
    certidao = servicos.guardar_resultado(
        s, solicitacao, documento=pdf, emitida_em=hoje - timedelta(days=5),
        valida_ate=hoje + timedelta(days=dias_para_vencer), situacao=situacao,
    )
    s.flush()
    return certidao


def test_reune_apenas_o_que_esta_vigente(s, titular_exemplo):
    _arquivar(s, titular_exemplo, "cndt", dias_para_vencer=100)
    _arquivar(s, titular_exemplo, "fgts_crf", dias_para_vencer=-1)     # vencida
    _arquivar(s, titular_exemplo, "rfb_pgfn_conjunta", dias_para_vencer=40,
              situacao=SituacaoCertidao.POSITIVA)                       # com débitos

    codigos = {c.tipo.codigo for c in certidoes_do_dossie(s, titular_exemplo.id)}
    assert codigos == {"cndt"}


def test_dossie_tem_folha_de_rosto_e_os_documentos(s, titular_exemplo):
    _arquivar(s, titular_exemplo, "cndt", dias_para_vencer=100)
    _arquivar(s, titular_exemplo, "fgts_crf", dias_para_vencer=20)

    conteudo, nome = montar(s, titular_exemplo.id)
    leitor = PdfReader(io.BytesIO(conteudo))

    assert nome.startswith("dossie_11222333000181_")
    assert len(leitor.pages) == 3  # folha de rosto + duas certidões
    rosto = leitor.pages[0].extract_text()
    assert "DOSSIE DE REGULARIDADE" in rosto
    assert "Escritorio Exemplo Ltda" in rosto or "Escritório Exemplo Ltda" in rosto
    assert "CNDT" in rosto and "CRF/FGTS" in rosto
    assert "valida ate" in rosto


def test_sem_certidao_vigente_explica_o_que_fazer(s, titular_exemplo):
    with pytest.raises(SemCertidoes, match="Emita ou anexe"):
        montar(s, titular_exemplo.id)


def test_apenas_a_versao_mais_recente_de_cada_tipo(s, titular_exemplo):
    _arquivar(s, titular_exemplo, "cndt", dias_para_vencer=30)
    recente = _arquivar(s, titular_exemplo, "cndt", dias_para_vencer=170)

    escolhidas = certidoes_do_dossie(s, titular_exemplo.id)
    assert [c.id for c in escolhidas] == [recente.id]
