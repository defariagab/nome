"""Configuração e caminhos do sistema.

Tudo mora numa única pasta de dados (por padrão ``~/.certidoes``) para que o
usuário final possa fazer backup copiando uma pasta só.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PACOTE = Path(__file__).resolve().parent


def _pasta_dados() -> Path:
    if valor := os.environ.get("CERTIDOES_DADOS"):
        return Path(valor).expanduser().resolve()
    return Path.home() / ".certidoes"


@dataclass
class Config:
    pasta_dados: Path = field(default_factory=_pasta_dados)
    host: str = os.environ.get("CERTIDOES_HOST", "127.0.0.1")
    porta: int = int(os.environ.get("CERTIDOES_PORTA", "8765"))
    # "simulador" não acessa a internet: usado em testes e na demonstração.
    # "navegador" usa o Playwright para operar os sites reais.
    motor: str = os.environ.get("CERTIDOES_MOTOR", "navegador")
    # Com o navegador visível o usuário acompanha (e socorre) a automação.
    navegador_visivel: bool = os.environ.get("CERTIDOES_NAVEGADOR_VISIVEL", "1") != "0"
    abrir_navegador_ao_iniciar: bool = os.environ.get("CERTIDOES_ABRIR", "1") != "0"
    #: quantas emissões de captcha de letras rodam ao mesmo tempo — é o que
    #: permite responder vários captchas em sequência, sem esperar entre eles
    paralelismo: int = int(os.environ.get("CERTIDOES_PARALELISMO", "4"))
    #: caminho de um Chrome/Chromium já instalado (opcional; evita novo download)
    caminho_navegador: str | None = os.environ.get("CERTIDOES_CHROMIUM") or None
    #: proxy corporativo, se houver (ex.: http://proxy.escritorio:3128)
    proxy: str | None = field(
        default_factory=lambda: os.environ.get("CERTIDOES_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or None
    )
    #: endereços que não passam pelo proxy
    proxy_excecoes: str = os.environ.get("CERTIDOES_PROXY_EXCECOES", "localhost,127.0.0.1")
    #: só para diagnóstico atrás de proxy que reescreve certificados
    ignorar_tls: bool = os.environ.get("CERTIDOES_IGNORAR_TLS", "0") == "1"

    @property
    def banco(self) -> Path:
        return self.pasta_dados / "certidoes.db"

    @property
    def url_banco(self) -> str:
        if url := os.environ.get("CERTIDOES_URL_BANCO"):
            return url
        return f"sqlite:///{self.banco}"

    @property
    def pasta_documentos(self) -> Path:
        return self.pasta_dados / "documentos"

    @property
    def pasta_sessoes(self) -> Path:
        """Sessões de navegador (ex.: login gov.br já autenticado)."""
        return self.pasta_dados / "sessoes"

    @property
    def pasta_catalogo(self) -> Path:
        return PACOTE / "catalogo"

    @property
    def pasta_receitas(self) -> Path:
        return PACOTE / "receitas"

    @property
    def pasta_web(self) -> Path:
        return PACOTE / "web"

    @property
    def arquivo_chave(self) -> Path:
        return self.pasta_dados / "chave.bin"

    def preparar(self) -> "Config":
        for pasta in (self.pasta_dados, self.pasta_documentos, self.pasta_sessoes):
            pasta.mkdir(parents=True, exist_ok=True)
        return self


config = Config().preparar()
