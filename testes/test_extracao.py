from datetime import date

from certidoes.automacao.extracao import analisar
from certidoes.automacao.pdf_simples import gerar
from certidoes.modelos import SituacaoCertidao

TEXTO_CNDT = """CERTIDAO NEGATIVA DE DEBITOS TRABALHISTAS
Nome: EMPRESA EXEMPLO LTDA (MATRIZ E FILIAIS)
CNPJ: 11.222.333/0001-81
Certidao n. 12345678/2026
Expedicao: 27/08/2026, as 09:15:22
Validade: 22/02/2027 - 180 (cento e oitenta) dias, contados da data de sua expedicao.
Codigo de Autenticacao: 1234-5678-90AB
"""


def test_le_o_que_o_documento_informa():
    dados = analisar(None, TEXTO_CNDT)
    assert dados["emitida_em"] == date(2026, 8, 27)
    assert dados["valida_ate"] == date(2027, 2, 22)
    assert dados["numero"] == "12345678/2026"
    assert dados["codigo_verificacao"] == "1234-5678-90AB"
    assert dados["situacao"] is SituacaoCertidao.NEGATIVA


def test_reconhece_positiva_com_efeito_de_negativa():
    texto = "CERTIDAO POSITIVA COM EFEITOS DE NEGATIVA DE DEBITOS"
    assert analisar(None, texto)["situacao"] is SituacaoCertidao.POSITIVA_COM_EFEITO_NEGATIVO


def test_reconhece_positiva():
    texto = "CERTIDAO POSITIVA DE DEBITOS. Constam debitos em nome do contribuinte."
    assert analisar(None, texto)["situacao"] is SituacaoCertidao.POSITIVA


def test_le_pdf_de_verdade():
    pdf = gerar(["Certidao n. 99/2026", "Validade: 01/12/2026", "CERTIDAO NEGATIVA"], "Teste")
    dados = analisar(pdf)
    assert dados["valida_ate"] == date(2026, 12, 1)
    assert dados["situacao"] is SituacaoCertidao.NEGATIVA


def test_documento_sem_datas_nao_inventa():
    dados = analisar(None, "documento sem qualquer data")
    assert dados["valida_ate"] is None
    assert dados["emitida_em"] is None


def test_validade_declarada_como_periodo_usa_a_data_final():
    """O CRF do FGTS diz "Validade: 17/08/2026 a 15/09/2026".

    Ler a primeira data fazia o sistema arquivar um certificado recém-emitido
    já como vencido — e cobrar renovação no mesmo dia.
    """
    from certidoes.automacao.extracao import data_de_validade

    texto = (
        "Certificado de Regularidade do FGTS - CRF\n"
        "Validade: \n 17/08/2026 a 15/09/2026\n"
        "Certificado Número: \n2026081704151857022076"
    )
    assert data_de_validade(texto).isoformat() == "2026-09-15"


def test_validade_simples_continua_valendo():
    from certidoes.automacao.extracao import data_de_validade

    assert data_de_validade("Validade: 26/09/2026").isoformat() == "2026-09-26"
    assert data_de_validade("válida até 01/01/2027").isoformat() == "2027-01-01"
