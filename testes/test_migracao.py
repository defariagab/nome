"""Um banco criado por versão anterior precisa continuar abrindo, com os dados."""

from sqlalchemy import select

from certidoes.banco import iniciar, motor, sessao
from certidoes.modelos import TipoCertidao


def _voltar_ao_nome_antigo():
    """Recria a situação de quem instalou antes da renomeação."""
    with motor.begin() as conexao:
        conexao.exec_driver_sql('ALTER TABLE tipo_certidao RENAME COLUMN "fonte" TO "receita"')


def test_coluna_renomeada_sem_perder_dados():
    with sessao() as s:
        cndt = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "cndt"))
        assert cndt.fonte == "cndt"
        quantos = len(list(s.scalars(select(TipoCertidao))))

    _voltar_ao_nome_antigo()
    with motor.begin() as conexao:
        colunas = {linha[1] for linha in conexao.exec_driver_sql("PRAGMA table_info(tipo_certidao)")}
        assert "receita" in colunas and "fonte" not in colunas

    iniciar()  # abrir o sistema aplica a migração

    with sessao() as s:
        cndt = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "cndt"))
        assert cndt.fonte == "cndt"                                  # o valor sobreviveu
        assert len(list(s.scalars(select(TipoCertidao)))) == quantos  # e nada sumiu


def test_migracao_e_idempotente():
    iniciar()
    iniciar()
    with sessao() as s:
        assert s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "cndt")).fonte == "cndt"


def test_banco_novo_ja_nasce_certo():
    with motor.begin() as conexao:
        colunas = {linha[1] for linha in conexao.exec_driver_sql("PRAGMA table_info(tipo_certidao)")}
    assert "fonte" in colunas
    assert "receita" not in colunas
