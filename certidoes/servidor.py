"""Sobe o servidor local e abre o painel no navegador."""

from __future__ import annotations

import logging
import threading
import webbrowser

import uvicorn

from .config import config

log = logging.getLogger("certidoes")


def _abrir_depois(url: str, segundos: float = 1.5) -> None:
    threading.Timer(segundos, lambda: webbrowser.open(url)).start()


def executar(abrir: bool | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    url = f"http://{config.host}:{config.porta}"
    print(f"\n  Certidões — painel em {url}")
    print(f"  Dados e documentos em {config.pasta_dados}")
    print("  Para encerrar, feche esta janela ou pressione Ctrl+C.\n")
    if abrir if abrir is not None else config.abrir_navegador_ao_iniciar:
        _abrir_depois(url)
    uvicorn.run(
        "certidoes.api.app:app",
        host=config.host,
        port=config.porta,
        log_level="warning",
        access_log=False,
    )
