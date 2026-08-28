"""Acesso ao banco de dados."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from .config import config
from .modelos import Base, Organizacao

_kwargs = {"future": True}
if config.url_banco.startswith("sqlite"):
    _kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

motor = create_engine(config.url_banco, **_kwargs)


@event.listens_for(motor, "connect")
def _configurar_sqlite(dbapi_conn, _record):  # pragma: no cover - depende do driver
    if config.url_banco.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")      # leitura simultânea à escrita
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


CriarSessao = sessionmaker(bind=motor, expire_on_commit=False, future=True)


@contextmanager
def sessao() -> Iterator[Session]:
    s = CriarSessao()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


#: (tabela, coluna antiga, coluna nova) — renomeações já aplicadas em campo.
#: Um banco que já existe precisa acompanhar o código sem perder nada.
RENOMEACOES = [
    ("tipo_certidao", "receita", "fonte"),
]

#: (tabela, coluna, definição) — colunas acrescentadas depois da primeira versão
COLUNAS_NOVAS = [
    ("certidao", "custo", "FLOAT DEFAULT 0"),
    ("tipo_certidao", "fontes", "JSON"),
    ("solicitacao", "fonte", "VARCHAR(60)"),
]


def _colunas(conexao, tabela: str) -> set[str]:
    try:
        linhas = conexao.exec_driver_sql(f"PRAGMA table_info({tabela})").fetchall()
    except Exception:
        return set()
    return {linha[1] for linha in linhas}


def migrar() -> None:
    """Ajusta bancos criados por versões anteriores, preservando os dados."""
    if not config.url_banco.startswith("sqlite"):
        return  # em outro banco, a migração é feita pela ferramenta do projeto
    with motor.begin() as conexao:
        for tabela, antiga, nova in RENOMEACOES:
            colunas = _colunas(conexao, tabela)
            if antiga in colunas and nova not in colunas:
                conexao.exec_driver_sql(
                    f'ALTER TABLE {tabela} RENAME COLUMN "{antiga}" TO "{nova}"'
                )
        for tabela, coluna, definicao in COLUNAS_NOVAS:
            colunas = _colunas(conexao, tabela)
            if colunas and coluna not in colunas:
                conexao.exec_driver_sql(
                    f'ALTER TABLE {tabela} ADD COLUMN "{coluna}" {definicao}'
                )


def iniciar() -> None:
    """Cria as tabelas, migra o que veio de versões anteriores e garante a
    organização padrão."""
    migrar()
    Base.metadata.create_all(motor)
    with sessao() as s:
        if not s.scalar(select(Organizacao).limit(1)):
            s.add(Organizacao(id=1, nome="Meu escritório"))
