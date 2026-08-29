"""Sobe o servidor local e abre o painel no navegador.

Só pode existir um painel por vez. Se o usuário clicar duas vezes no atalho
— e ele clica —, a segunda vez apenas traz o painel que já está aberto para a
frente, em vez de abrir uma segunda aba idêntica sobre um servidor que nem
chegou a subir.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from .config import config

log = logging.getLogger("certidoes")


def _abrir_depois(url: str, segundos: float = 1.5) -> None:
    threading.Timer(segundos, lambda: webbrowser.open(url)).start()


def _painel_ja_aberto(url: str) -> bool:
    """Já existe um painel nosso respondendo neste endereço?

    Perguntamos ao próprio programa (``/api/saude``) em vez de só testar a
    porta: se outro programa qualquer estiver usando a porta, queremos avisar,
    não abrir o navegador em cima dele. O proxy da máquina é ignorado de
    propósito — o endereço é local.
    """
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with abridor.open(f"{url}/api/saude", timeout=2) as resposta:
            return bool(json.load(resposta).get("ok"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return False


def executar(abrir: bool | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    url = f"http://{config.host}:{config.porta}"
    quer_abrir = abrir if abrir is not None else config.abrir_navegador_ao_iniciar

    if _painel_ja_aberto(url):
        print(f"\n  O painel já está aberto em {url}.")
        print("  Trouxe para a frente a janela que já existia — não abri outra.\n")
        if quer_abrir:
            webbrowser.open(url)
        return

    print(f"\n  Certidões — painel em {url}")
    print(f"  Dados e documentos em {config.pasta_dados}")
    print("  Para encerrar, feche esta janela ou pressione Ctrl+C.\n")
    if quer_abrir:
        _abrir_depois(url)
    try:
        uvicorn.run(
            "certidoes.api.app:app",
            host=config.host,
            port=config.porta,
            log_level="warning",
            access_log=False,
        )
    except (OSError, SystemExit) as erro:
        # A porta ficou ocupada entre a checagem e o start, ou outro programa
        # da máquina usa a 8765 (o uvicorn encerra com SystemExit nesse caso).
        # Sem isto o usuário vê um traceback e não entende o que aconteceu.
        detalhe = f": {erro}" if isinstance(erro, OSError) else "."
        print(f"\n  Não consegui usar a porta {config.porta}{detalhe}")
        print("  Se o painel já estiver aberto, use a janela que existe.")
        print("  Se outro programa usa esta porta, escolha outra assim:")
        print("    Windows: set CERTIDOES_PORTA=8766 e clique em iniciar.bat")
        print("    macOS/Linux: CERTIDOES_PORTA=8766 ./iniciar.command\n")
