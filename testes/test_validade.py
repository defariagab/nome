from datetime import date

from certidoes.validade import Status, avaliar, calcular_validade, data_de_renovacao


def test_validade_conta_o_dia_da_emissao():
    assert calcular_validade(date(2026, 1, 1), 180) == date(2026, 6, 29)
    assert calcular_validade(date(2026, 1, 1), 1) == date(2026, 1, 1)


def test_status_por_prazo():
    hoje = date(2026, 8, 27)
    assert avaliar(None, hoje=hoje).status is Status.AUSENTE
    assert avaliar(date(2026, 8, 26), hoje=hoje).status is Status.VENCIDA
    assert avaliar(date(2026, 8, 27), hoje=hoje).status is Status.VENCE_EM_BREVE
    assert avaliar(date(2026, 9, 11), hoje=hoje).status is Status.VENCE_EM_BREVE
    assert avaliar(date(2026, 9, 12), hoje=hoje).status is Status.VIGENTE


def test_certidao_positiva_nao_comprova_regularidade():
    vigencia = avaliar(date(2027, 1, 1), hoje=date(2026, 8, 27), regular=False)
    assert vigencia.status is Status.IRREGULAR
    assert vigencia.precisa_renovar


def test_antecedencia_configuravel():
    hoje = date(2026, 8, 27)
    assert avaliar(date(2026, 9, 20), hoje=hoje, dias_antecedencia=30).status is Status.VENCE_EM_BREVE
    assert avaliar(date(2026, 9, 20), hoje=hoje, dias_antecedencia=5).status is Status.VIGENTE


def test_data_de_renovacao():
    assert data_de_renovacao(date(2026, 9, 30), 15) == date(2026, 9, 15)


def test_urgencia_ordena_o_painel():
    assert Status.VENCIDA.prioridade < Status.VENCE_EM_BREVE.prioridade < Status.VIGENTE.prioridade
    assert Status.IRREGULAR.prioridade < Status.VENCIDA.prioridade
