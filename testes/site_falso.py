"""Réplica local de um portal de certidões, para testar o motor de navegador.

Reproduz o que os sites reais fazem e que costuma quebrar automação:
formulário, captcha de imagem, recusa quando a resposta erra e entrega do
documento como download.
"""

from __future__ import annotations

import base64
import random
import string
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from certidoes.automacao.pdf_simples import gerar

RESPOSTA_CAPTCHA = {"valor": ""}


def _svg(texto: str) -> str:
    letras = "".join(
        f'<text x="{12 + i * 26}" y="40" font-size="30" font-family="monospace" '
        f'fill="#123" transform="rotate({-8 + i * 4} {20 + i * 26} 40)">{c}</text>'
        for i, c in enumerate(texto)
    )
    # riscos por cima, como nos captchas de verdade: sem eles a imagem de
    # teste seria limpa demais para valer como réplica
    ruido = "".join(
        f'<line x1="{i * 7}" y1="{(i * 13) % 60}" x2="{180 - i * 5}" y2="{(i * 29) % 60}" '
        f'stroke="#9ab" stroke-width="1"/>'
        for i in range(24)
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="60">'
        f'<rect width="180" height="60" fill="#eef"/>{ruido}{letras}</svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


PAGINA = """<!doctype html><html lang="pt-BR"><body>
<h1>Emissao de certidao</h1>
<form method="post" action="/emitir">
  <input type="text" id="doc" name="doc">
  <img id="cap" alt="captcha">
  <script>
    // como no site do TST: o elemento existe antes de a imagem chegar
    setTimeout(function () {{ document.getElementById('cap').src = "{captcha}"; }}, 700);
  </script>
  <input type="text" id="resp" name="resp">
  <input type="text" id="escondido" name="escondido" style="display:none">
  <input type="radio" id="tipo-cnpj" name="tipo" value="cnpj">
  <button type="submit" id="ok">Emitir</button>
</form>
<form method="post" action="/emitir" target="_blank">
  <input type="hidden" name="doc" value="popup">
  <input type="hidden" name="resp" value="janela-nova">
  <button type="submit" id="ok-popup">Emitir em nova janela</button>
</form>
</body></html>"""

PAGINA_CRF = """<!doctype html><html lang="pt-BR"><body>
<form method="post" action="/crf">
  <input type="text" id="ins" name="ins">
  <select id="uf" name="uf"><option value="">-</option><option value="SP">SP</option></select>
  <button type="submit" id="consultar">Consultar</button>
</form>
</body></html>"""


class Manipulador(BaseHTTPRequestHandler):
    def log_message(self, *_args):  # silencia o log do servidor de teste
        pass

    def _responder(self, corpo: bytes, tipo: str, cabecalhos: dict | None = None):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for chave, valor in (cabecalhos or {}).items():
            self.send_header(chave, valor)
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path.startswith("/crf-certificado"):
            corpo = (
                "<html><body><h1>Certificado de Regularidade do FGTS - CRF</h1>"
                "<p>Numero do CRF: 2026082900001</p>"
                "<p>Validade: 26/09/2026</p></body></html>"
            )
            self._responder(corpo.encode(), "text/html; charset=utf-8")
            return
        if self.path.startswith("/crf"):
            self._responder(PAGINA_CRF.encode(), "text/html; charset=utf-8")
            return
        if self.path.startswith("/favicon"):
            # o navegador pede o ícone sozinho: se isso sorteasse um captcha
            # novo, a réplica deixaria de reproduzir o site
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        RESPOSTA_CAPTCHA["valor"] = "".join(random.choices(string.ascii_lowercase, k=5))
        pagina = PAGINA.format(captcha=_svg(RESPOSTA_CAPTCHA["valor"]))
        self._responder(pagina.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        campos = parse_qs(self.rfile.read(tamanho).decode())

        if self.path == "/crf":
            if campos.get("ins", [""])[0] == "00000000000000":
                # a Caixa responde 200 com uma pagina que parece certificado
                corpo = (
                    "<html><body><h1>Situacao de Regularidade do Empregador</h1>"
                    "<p>Nao foi possivel verificar a regularidade junto a CAIXA. "
                    "Solicitamos tentar mais tarde.</p></body></html>"
                )
                self._responder(corpo.encode(), "text/html; charset=utf-8")
                return
            if not campos.get("uf", [""])[0]:
                self._responder(b"<html><body>Informe a UF</body></html>", "text/html; charset=utf-8")
                return
            # Como na Caixa: a consulta responde uma pagina de resultado, e o
            # certificado em si so aparece depois de clicar no link.
            corpo = (
                "<html><body><h1>Situacao de Regularidade do Empregador</h1>"
                f"<p>Inscricao: {campos.get('ins', [''])[0]}</p>"
                "<p>A empresa abaixo identificada esta REGULAR no FGTS.</p>"
                "<a href=\'/crf-certificado\'>Obtenha o Certificado de "
                "Regularidade do FGTS - CRF</a></body></html>"
            )
            self._responder(corpo.encode(), "text/html; charset=utf-8")
            return

        if campos.get("resp", [""])[0] == "janela-nova":
            # alguns órgãos entregam o arquivo numa aba nova
            self._responder(
                gerar(["Certidao n. 7777/2026", "Validade: 01/01/2027", "CERTIDAO NEGATIVA"],
                      "Certidao em nova janela"),
                "application/pdf",
                {"Content-Disposition": 'attachment; filename="certidao.pdf"'},
            )
            return

        if campos.get("resp", [""])[0].strip().lower() != RESPOSTA_CAPTCHA["valor"]:
            self._responder(
                b"<html><body>Os caracteres digitados nao conferem com a imagem.</body></html>",
                "text/html; charset=utf-8",
            )
            return

        pdf = gerar(
            [
                f"Inscricao: {campos.get('doc', [''])[0]}",
                "Certidao n. 4242/2026",
                "Expedicao: 27/08/2026",
                "Validade: 22/02/2027",
                "CERTIDAO NEGATIVA",
            ],
            "Certidao de teste",
        )
        self._responder(pdf, "application/pdf", {"Content-Disposition": 'attachment; filename="certidao.pdf"'})


class SiteFalso:
    def __init__(self):
        self.servidor = HTTPServer(("127.0.0.1", 0), Manipulador)
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.servidor.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.servidor.shutdown()
        self.servidor.server_close()
