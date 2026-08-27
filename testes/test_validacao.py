"""Página de erro não pode virar certidão no acervo.

O texto abaixo é o de um documento real que o sistema chegou a arquivar como
certificado válido: a Caixa respondeu que não conseguiu verificar a
regularidade, e a conferência de então se contentou com a palavra
"Regularidade" do cabeçalho.
"""

from datetime import date

import pytest

from certidoes import servicos, validacao
from certidoes.automacao.extracao import analisar, situacao
from certidoes.automacao.pdf_simples import gerar
from certidoes.modelos import SituacaoCertidao

ERRO_DA_CAIXA = """Dúvidas mais Frequentes | Início | V - 2.3
Situação de Regularidade do
Empregador
Inscrição:
 04.847.418/0001-90
O uso destas informações para os fins previstos em lei deve ser precedido de verificação de
autenticidade no site da Caixa:www.caixa.gov.br
Não foi possível verificar a regularidade junto à CAIXA. Solicitamos tentar mais tarde. Caso
persista solicitamos comparecer a uma das Agências da CAIXA para obter esclarecimentos
adicionais.
Voltar"""

CRF_VALIDO = """Certificado de Regularidade do FGTS - CRF
Inscrição: 04.847.418/0001-90
Razão Social: EMPRESA EXEMPLO LTDA
Certificado numero: 2026082700112233
Validade: 27/08/2026 a 25/09/2026"""


def test_o_documento_que_nao_devia_ter_sido_arquivado():
    dados = analisar(None, ERRO_DA_CAIXA)
    veredito = validacao.avaliar(
        ERRO_DA_CAIXA, situacao=dados["situacao"],
        valida_ate=dados["valida_ate"], numero=dados["numero"],
    )
    assert not veredito
    assert "indisponibilidade" in veredito.motivo
    assert "tentar de novo mais tarde" in veredito.motivo


def test_cabecalho_com_a_palavra_regularidade_nao_e_certidao_negativa():
    assert situacao(ERRO_DA_CAIXA) is SituacaoCertidao.NAO_IDENTIFICADA
    assert situacao("Situação de Regularidade do Empregador") is SituacaoCertidao.NAO_IDENTIFICADA


def test_certificado_de_verdade_passa():
    dados = analisar(None, CRF_VALIDO)
    assert dados["situacao"] is SituacaoCertidao.NEGATIVA
    assert validacao.avaliar(
        CRF_VALIDO, situacao=dados["situacao"],
        valida_ate=dados["valida_ate"], numero=dados["numero"],
    )


@pytest.mark.parametrize("texto", [
    "Sistema indisponível no momento.",
    "Ocorreu um erro ao processar sua solicitação.",
    "Serviço em manutenção. Tente novamente mais tarde.",
    "Prezado usuário, o seu acesso foi bloqueado por possuir atributos que o caracteriza "
    "como um acesso automatizado.",
])
def test_avisos_de_indisponibilidade_sao_reconhecidos(texto):
    assert not validacao.avaliar(texto)


def test_documento_vazio_e_recusado():
    veredito = validacao.avaliar("")
    assert not veredito
    assert "vazio ou ilegível" in veredito.motivo


def test_pagina_qualquer_sem_marca_de_certidao_e_recusada():
    veredito = validacao.avaliar("Bem-vindo ao portal. Escolha um serviço no menu.")
    assert not veredito
    assert "não parece uma certidão" in veredito.motivo


def test_anexo_manual_tambem_recusa_pagina_de_erro(s, titular_exemplo):
    """Nem por engano do usuário uma página de erro entra no acervo."""
    from sqlalchemy import select

    from certidoes.modelos import TipoCertidao

    fgts = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "fgts_crf"))
    solicitacao = servicos.solicitar(s, titular_exemplo.id, fgts.id)
    s.flush()
    pdf_de_erro = gerar(ERRO_DA_CAIXA.splitlines(), titulo="Situacao de Regularidade")

    with pytest.raises(servicos.ErroDeUso, match="indisponibilidade"):
        servicos.anexar_documento(s, solicitacao.id, pdf_de_erro)


def test_anexo_manual_aceita_certificado_de_verdade(s, titular_exemplo):
    from sqlalchemy import select

    from certidoes.modelos import TipoCertidao

    fgts = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "fgts_crf"))
    solicitacao = servicos.solicitar(s, titular_exemplo.id, fgts.id)
    s.flush()
    pdf = gerar(CRF_VALIDO.splitlines(), titulo="Certificado de Regularidade do FGTS")

    certidao = servicos.anexar_documento(s, solicitacao.id, pdf, valida_ate=date(2026, 9, 25))
    assert certidao.situacao is SituacaoCertidao.NEGATIVA
