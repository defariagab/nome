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


def iniciar() -> None:
    """Cria as tabelas e garante a organização padrão."""
    Base.metadata.create_all(motor)
    with sessao() as s:
        if not s.scalar(select(Organizacao).limit(1)):
            s.add(Organizacao(id=1, nome="Meu escritório"))
