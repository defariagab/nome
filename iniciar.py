#!/usr/bin/env python3
"""Abre o sistema de certidões.

Dê dois cliques neste arquivo (ou rode `python iniciar.py`). Na primeira vez
ele instala o que falta e prepara a pasta de dados.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
NECESSARIOS = ["fastapi", "uvicorn", "sqlalchemy", "yaml", "cryptography", "pypdf", "multipart"]


def _falta_algo() -> bool:
    import importlib.util

    return any(importlib.util.find_spec(nome) is None for nome in NECESSARIOS)


def _instalar() -> None:
    print("Preparando o sistema pela primeira vez. Isso leva alguns minutos...\n")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(RAIZ / "requirements.txt")]
    )


def principal() -> int:
    if sys.version_info < (3, 10):
        print("É preciso Python 3.10 ou mais novo.")
        return 1
    if _falta_algo():
        try:
            _instalar()
        except subprocess.CalledProcessError:
            print("\nNão consegui instalar as dependências automaticamente.")
            print("Abra o terminal na pasta do programa e rode:")
            print(f"  {sys.executable} -m pip install -r requirements.txt")
            return 1
    sys.path.insert(0, str(RAIZ))
    from certidoes.servidor import executar

    executar()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
