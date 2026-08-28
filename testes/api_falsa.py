"""Uma API de certidões de mentira, para exercitar o motor de API."""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from certidoes.automacao.pdf_simples import gerar

TOKEN = "token-de-teste"


class Manipulador(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def _json(self, corpo: dict, status: int = 200):
        dados = json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        partes = urlparse(self.path)
        consulta = parse_qs(partes.query)
        ni = consulta.get("ni", [""])[0]

        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self._json({"mensagem": "token invalido"}, 401)
            return
        if partes.path.endswith("/limite"):
            self._json({"mensagem": "muitas chamadas"}, 429)
            return
        if ni == "00000000000000":
            self._json({"mensagem": "Contribuinte com pendencias impeditivas"})
            return
        if ni == "11111111111111":
            self._json({"dados": {"numeroCertidao": "sem-arquivo"}})
            return

        pdf = gerar(
            [f"Inscricao: {ni}", "Certidao n. API-2026/0001",
             "Emissao: 28/08/2026", "Validade: 24/02/2027", "CERTIDAO NEGATIVA"],
            titulo="Certidao Negativa de Debitos",
        )
        self._json({"dados": {
            "certidao": base64.b64encode(pdf).decode(),
            "numeroCertidao": "API-2026/0001",
            "dataEmissao": "28/08/2026",
            "dataValidade": "24/02/2027",
            "tipoCertidao": "Negativa",
        }})


class ApiFalsa:
    def __init__(self):
        self.servidor = HTTPServer(("127.0.0.1", 0), Manipulador)
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.servidor.server_address[1]}/consulta-cnd/certidao"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.servidor.shutdown()
        self.servidor.server_close()
