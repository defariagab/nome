from datetime import date, timedelta

import pytest
from sqlalchemy import select

from certidoes import agenda, servicos
from certidoes.modelos import EstadoSolicitacao, SituacaoCertidao, Solicitacao, TipoCertidao
from certidoes.validade import Status


def tipo_por_codigo(s, codigo: str) -> TipoCertidao:
    return s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == codigo))


def test_recusa_documento_invalido(s):
    with pytest.raises(servicos.ErroDeUso, match="inválido"):
        servicos.salvar_titular(s, {"nome": "Fulano", "documento": "123"})


def test_recusa_titular_duplicado(s, titular_exemplo):
    with pytest.raises(servicos.ErroDeUso, match="Já existe"):
        servicos.salvar_titular(s, {"nome": "Outro nome", "documento": "11222333000181"})


def test_tipos_aplicaveis_respeitam_pf_e_pj(s, titular_exemplo):
    codigos = {t.codigo for t in servicos.tipos_aplicaveis(s, titular_exemplo)}
    assert "cndt" in codigos
    assert "tj_falencia_concordata" in codigos  # exigida de pessoa jurídica

    pessoa = servicos.salvar_titular(s, {"nome": "Fulano de Tal", "documento": "529.982.247-25"})
    codigos_pf = {t.codigo for t in servicos.tipos_aplicaveis(s, pessoa)}
    assert "tj_falencia_concordata" not in codigos_pf


def test_painel_mostra_ausente_ate_a_primeira_emissao(s, titular_exemplo):
    cndt = tipo_por_codigo(s, "cndt")
    servicos.definir_monitoramentos(s, titular_exemplo.id, [cndt.id])
    s.flush()

    linhas = servicos.painel(s)
    assert len(linhas) == 1
    assert linhas[0]["status"] == Status.AUSENTE.value
    assert linhas[0]["sigla"] == "CNDT"


def test_arquivar_resultado_substitui_a_certidao_anterior(s, titular_exemplo):
    cndt = tipo_por_codigo(s, "cndt")
    servicos.definir_monitoramentos(s, titular_exemplo.id, [cndt.id])

    primeira = servicos.solicitar(s, titular_exemplo.id, cndt.id)
    servicos.guardar_resultado(
        s, primeira, documento=b"%PDF-1.4 primeira",
        emitida_em=date(2026, 1, 10), valida_ate=date(2026, 7, 8),
        situacao=SituacaoCertidao.NEGATIVA,
    )
    segunda = servicos.solicitar(s, titular_exemplo.id, cndt.id)
    segunda.estado = EstadoSolicitacao.CONCLUIDA
    nova = servicos.guardar_resultado(
        s, segunda, documento=b"%PDF-1.4 segunda",
        emitida_em=date(2026, 8, 1), valida_ate=date(2027, 1, 28),
        situacao=SituacaoCertidao.NEGATIVA,
    )
    s.flush()

    vigente = servicos.certidao_vigente(s, titular_exemplo.id, cndt.id)
    assert vigente.id == nova.id
    assert vigente.arquivo_hash != primeira.certidao_id


def test_validade_padrao_quando_o_documento_nao_informa(s, titular_exemplo):
    fgts = tipo_por_codigo(s, "fgts_crf")  # 30 dias no catálogo
    solicitacao = servicos.solicitar(s, titular_exemplo.id, fgts.id)
    certidao = servicos.guardar_resultado(
        s, solicitacao, documento=b"%PDF-1.4 x", emitida_em=date(2026, 8, 1), valida_ate=None
    )
    assert certidao.valida_ate == date(2026, 8, 30)


def test_nao_duplica_solicitacao_em_andamento(s, titular_exemplo):
    cndt = tipo_por_codigo(s, "cndt")
    primeira = servicos.solicitar(s, titular_exemplo.id, cndt.id)
    s.flush()
    assert servicos.solicitar(s, titular_exemplo.id, cndt.id).id == primeira.id


def test_renovacao_automatica_pega_o_que_vence(s, titular_exemplo):
    cndt = tipo_por_codigo(s, "cndt")
    servicos.definir_monitoramentos(s, titular_exemplo.id, [cndt.id], dias_antecedencia=15)
    solicitacao = servicos.solicitar(s, titular_exemplo.id, cndt.id)
    solicitacao.estado = EstadoSolicitacao.CONCLUIDA
    hoje = date.today()
    servicos.guardar_resultado(
        s, solicitacao, documento=b"%PDF-1.4 x",
        emitida_em=hoje - timedelta(days=170), valida_ate=hoje + timedelta(days=10),
        situacao=SituacaoCertidao.NEGATIVA,
    )
    s.commit()

    assert len(agenda.varrer()) == 1
    assert s.scalar(select(Solicitacao).where(Solicitacao.origem == "renovacao")) is not None
    assert agenda.varrer() == []  # não duplica enquanto a primeira não termina


def test_certidao_positiva_nao_entra_em_renovacao_automatica(s, titular_exemplo):
    cndt = tipo_por_codigo(s, "cndt")
    servicos.definir_monitoramentos(s, titular_exemplo.id, [cndt.id])
    solicitacao = servicos.solicitar(s, titular_exemplo.id, cndt.id)
    solicitacao.estado = EstadoSolicitacao.CONCLUIDA
    servicos.guardar_resultado(
        s, solicitacao, documento=b"%PDF-1.4 x",
        emitida_em=date.today(), valida_ate=date.today() + timedelta(days=100),
        situacao=SituacaoCertidao.POSITIVA,
    )
    s.commit()

    linhas = servicos.painel(s)
    assert linhas[0]["status"] == Status.IRREGULAR.value
    assert agenda.varrer() == []
