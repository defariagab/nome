#!/usr/bin/env python3
"""Abre o sistema de certidões.

Dê dois cliques neste arquivo (ou rode `python iniciar.py`). Na primeira vez
ele instala tudo o que o sistema precisa — inclusive o navegador usado para
falar com os sites dos órgãos — e depois abre o painel.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
BIBLIOTECAS = ["fastapi", "uvicorn", "sqlalchemy", "yaml", "cryptography", "pypdf", "multipart",
               "playwright"]


def aviso(texto: str = "") -> None:
    print(texto, flush=True)


def _faltam_bibliotecas() -> bool:
    import importlib.util

    return any(importlib.util.find_spec(nome) is None for nome in BIBLIOTECAS)


def _navegador_instalado() -> bool:
    """O Chromium do Playwright já foi baixado?"""
    if os.environ.get("CERTIDOES_CHROMIUM"):
        return Path(os.environ["CERTIDOES_CHROMIUM"]).exists()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch(headless=True)
            navegador.close()
        return True
    except Exception:
        return False


def _rodar(comando: list[str], descricao: str) -> bool:
    aviso(f"  {descricao}...")
    try:
        subprocess.check_call(comando)
        return True
    except (subprocess.CalledProcessError, OSError) as erro:
        aviso(f"  Não deu certo: {erro}")
        return False


def preparar() -> bool:
    """Instala o que falta. Devolve False se algo essencial não pôde ser instalado."""
    precisa_bibliotecas = _faltam_bibliotecas()
    if precisa_bibliotecas:
        aviso("\nPreparando o sistema pela primeira vez.")
        aviso("Isso pode levar alguns minutos e só acontece uma vez.\n")
        if not _rodar(
            [sys.executable, "-m", "pip", "install", "-r", str(RAIZ / "requirements.txt")],
            "Instalando as bibliotecas",
        ):
            aviso("\nNão consegui instalar as bibliotecas automaticamente.")
            aviso("Abra o Prompt de Comando na pasta do programa e digite:")
            aviso(f"  {sys.executable} -m pip install -r requirements.txt")
            return False

    if not _navegador_instalado():
        aviso("\nFalta o navegador que conversa com os sites dos órgãos.")
        if _rodar(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            "Baixando o navegador (cerca de 150 MB)",
        ):
            aviso("  Navegador pronto.")
        else:
            # Sem navegador o sistema ainda serve para controlar validade e
            # arquivar PDFs anexados à mão: não é motivo para não abrir.
            aviso("\n  Sem o navegador, a emissão automática fica indisponível.")
            aviso("  O controle de validade e o arquivo de PDFs continuam funcionando.")
            aviso("  Para tentar de novo depois, digite no Prompt de Comando:")
            aviso(f"    {sys.executable} -m playwright install chromium")
    return True


def principal() -> int:
    if sys.version_info < (3, 10):
        aviso("É preciso o Python 3.10 ou mais novo. Baixe em https://www.python.org/downloads/")
        return 1
    if not preparar():
        return 1
    sys.path.insert(0, str(RAIZ))
    from certidoes.servidor import executar

    executar()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(principal())
    except KeyboardInterrupt:
        aviso("\nEncerrado.")
