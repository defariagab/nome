"""Cofre de credenciais.

Senhas do gov.br são dados sensíveis de terceiros. Aqui elas nunca são
gravadas em texto puro: o banco guarda apenas o texto cifrado, e a chave
fica num arquivo separado, com permissão restrita ao dono.
"""

from __future__ import annotations

import base64
import os
import stat

from cryptography.fernet import Fernet, InvalidToken

from .config import config


class SegredoIndisponivel(RuntimeError):
    """A chave mudou ou o dado foi corrompido: o segredo não pode ser lido."""


def _carregar_chave() -> bytes:
    caminho = config.arquivo_chave
    if caminho.exists():
        return caminho.read_bytes()
    chave = Fernet.generate_key()
    caminho.write_bytes(chave)
    try:
        os.chmod(caminho, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:  # pragma: no cover - sistemas sem suporte a chmod
        pass
    return chave


_cofre: Fernet | None = None


def cofre() -> Fernet:
    global _cofre
    if _cofre is None:
        _cofre = Fernet(_carregar_chave())
    return _cofre


def cifrar(texto: str | None) -> str | None:
    if texto is None or texto == "":
        return None
    return cofre().encrypt(texto.encode()).decode()


def decifrar(texto: str | None) -> str | None:
    if not texto:
        return None
    try:
        return cofre().decrypt(texto.encode()).decode()
    except InvalidToken as erro:
        raise SegredoIndisponivel(
            "Não foi possível ler a credencial: o arquivo de chave foi trocado ou perdido. "
            "Cadastre a credencial novamente."
        ) from erro


def mascarar(texto: str | None) -> str:
    """Representação segura para exibir na tela (nunca devolve o segredo)."""
    if not texto:
        return ""
    return "•" * 8


def impressao_digital(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados[:12]).decode()
