"""Um painel por vez.

O usuário clica duas vezes no atalho — e clicava duas vezes no atalho. A
segunda vez abria uma aba idêntica sobre um servidor que nem chegava a subir.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from certidoes import servidor


class _Saude(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        corpo = json.dumps({"ok": True, "versao": "teste", "motor": "simulador"}).encode()
        self.send_response(200 if self.path == "/api/saude" else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)


def test_reconhece_um_painel_ja_aberto():
    http = HTTPServer(("127.0.0.1", 0), _Saude)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        assert servidor._painel_ja_aberto(f"http://127.0.0.1:{http.server_address[1]}")
    finally:
        http.shutdown()
        http.server_close()


def test_porta_livre_nao_e_confundida_com_painel():
    # porta fechada: o servidor tem de subir normalmente
    livre = HTTPServer(("127.0.0.1", 0), _Saude)
    porta = livre.server_address[1]
    livre.server_close()
    assert not servidor._painel_ja_aberto(f"http://127.0.0.1:{porta}")


def test_segundo_clique_apenas_traz_o_painel_existente(monkeypatch):
    http = HTTPServer(("127.0.0.1", 0), _Saude)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    abertos: list[str] = []
    subiu: list[str] = []
    monkeypatch.setattr(servidor.config, "porta", http.server_address[1])
    monkeypatch.setattr(servidor.config, "host", "127.0.0.1")
    monkeypatch.setattr(servidor.webbrowser, "open", lambda url: abertos.append(url))
    monkeypatch.setattr(servidor.uvicorn, "run", lambda *a, **k: subiu.append("subiu"))
    try:
        servidor.executar(abrir=True)
    finally:
        http.shutdown()
        http.server_close()

    assert not subiu, "não pode subir um segundo servidor na mesma porta"
    assert abertos == [f"http://127.0.0.1:{http.server_address[1]}"]
