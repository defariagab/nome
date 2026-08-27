"""Ambiente isolado para os testes: pasta de dados temporária e motor simulado."""

import os
import tempfile
from pathlib import Path

PASTA = Path(tempfile.mkdtemp(prefix="certidoes-testes-"))
os.environ["CERTIDOES_DADOS"] = str(PASTA)
os.environ["CERTIDOES_MOTOR"] = "simulador"
os.environ["CERTIDOES_ABRIR"] = "0"

import pytest  # noqa: E402

from certidoes import catalogo  # noqa: E402
from certidoes.banco import CriarSessao, iniciar, motor  # noqa: E402
from certidoes.modelos import Base  # noqa: E402


@pytest.fixture(autouse=True)
def banco_limpo():
    Base.metadata.create_all(motor)
    # certidao e solicitacao se referenciam mutuamente: apaga com as chaves
    # estrangeiras desligadas em vez de tentar ordenar as tabelas.
    with motor.begin() as conexao:
        conexao.exec_driver_sql("PRAGMA foreign_keys=OFF")
        for tabela in Base.metadata.tables.values():
            conexao.execute(tabela.delete())
        conexao.exec_driver_sql("PRAGMA foreign_keys=ON")
    iniciar()
    catalogo.carregar()
    yield


@pytest.fixture
def s():
    sessao = CriarSessao()
    try:
        yield sessao
        sessao.commit()
    finally:
        sessao.close()


@pytest.fixture
def titular_exemplo(s):
    from certidoes import servicos

    titular = servicos.salvar_titular(s, {
        "nome": "Escritório Exemplo Ltda",
        "documento": "11.222.333/0001-81",
        "uf": "SP",
        "municipio": "São Paulo",
    })
    s.commit()
    return titular
