"""Arquivamento dos PDFs emitidos."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

from .config import config

_SEGURO = re.compile(r"[^A-Za-z0-9._-]+")


def _fatiar(texto: str, tamanho: int = 60) -> str:
    limpo = _SEGURO.sub("-", texto).strip("-")
    return limpo[:tamanho] or "arquivo"


def hash_conteudo(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def guardar(
    dados: bytes,
    *,
    documento: str,
    emitida_em: date,
    nome_arquivo: str,
) -> tuple[str, str]:
    """Grava o documento e devolve ``(caminho_relativo, hash)``.

    A pasta é organizada por titular e ano para que o acervo continue
    navegável direto pelo explorador de arquivos, sem depender do sistema.
    O nome do arquivo segue o padrão definido pelo escritório.
    """
    digest = hash_conteudo(dados)
    pasta = config.pasta_documentos / _fatiar(documento) / str(emitida_em.year)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = _sem_colidir(pasta, nome_arquivo, dados, digest)
    if not destino.exists():
        destino.write_bytes(dados)
    return str(destino.relative_to(config.pasta_documentos)), digest


def _sem_colidir(pasta: Path, nome: str, dados: bytes, digest: str) -> Path:
    """Duas certidões diferentes com o mesmo nome não podem se sobrescrever."""
    destino = pasta / nome
    if not destino.exists() or hash_conteudo(destino.read_bytes()) == digest:
        return destino
    base, _, extensao = nome.rpartition(".")
    return pasta / f"{base}_{digest[:8]}.{extensao}"


def caminho_absoluto(relativo: str) -> Path:
    """Resolve um caminho gravado no banco, barrando fuga da pasta de documentos."""
    base = config.pasta_documentos.resolve()
    alvo = (base / relativo).resolve()
    if not alvo.is_relative_to(base):
        raise ValueError("Caminho de documento inválido")
    return alvo


def ler(relativo: str) -> bytes:
    return caminho_absoluto(relativo).read_bytes()
