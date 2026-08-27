import pytest

from certidoes.documento import cnpj_valido, cpf_valido, formatar, tipo_pessoa, valido


@pytest.mark.parametrize("cpf", ["529.982.247-25", "52998224725", "111.444.777-35"])
def test_cpf_valido(cpf):
    assert cpf_valido(cpf)


@pytest.mark.parametrize("cpf", ["529.982.247-24", "111.111.111-11", "123", ""])
def test_cpf_invalido(cpf):
    assert not cpf_valido(cpf)


@pytest.mark.parametrize("cnpj", ["11.222.333/0001-81", "11222333000181"])
def test_cnpj_valido(cnpj):
    assert cnpj_valido(cnpj)


@pytest.mark.parametrize("cnpj", ["11.222.333/0001-80", "00.000.000/0000-00"])
def test_cnpj_invalido(cnpj):
    assert not cnpj_valido(cnpj)


def test_formatacao_e_tipo():
    assert formatar("52998224725") == "529.982.247-25"
    assert formatar("11222333000181") == "11.222.333/0001-81"
    assert tipo_pessoa("52998224725") == "PF"
    assert tipo_pessoa("11222333000181") == "PJ"
    assert valido("11.222.333/0001-81")
    assert not valido("999")
