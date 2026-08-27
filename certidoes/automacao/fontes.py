"""Carregamento das fontes declarativas (YAML)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..config import config
from .tipos import Passo, Fonte


def _converter(bruto: dict) -> Fonte:
    passos = [Passo(acao=p["acao"], dados={k: v for k, v in p.items() if k != "acao"})
              for p in bruto.get("passos", [])]
    return Fonte(
        codigo=bruto["codigo"],
        nome=bruto.get("nome", bruto["codigo"]),
        url=bruto.get("url", ""),
        passos=passos,
        resultado=bruto.get("resultado", "download"),
        verificado_em=bruto.get("verificado_em"),
        perfil=bruto.get("perfil"),
        ao_falhar=bruto.get("ao_falhar", "falhar"),
        _paralelizavel=bruto.get("paralelizavel", True),
    )


@lru_cache(maxsize=None)
def carregar_fonte(codigo: str) -> Fonte | None:
    caminho = config.pasta_fontes / f"{codigo}.yaml"
    if not caminho.exists():
        return None
    return _converter(yaml.safe_load(caminho.read_text(encoding="utf-8")))


def listar_fontes() -> list[Fonte]:
    fontes = []
    for caminho in sorted(Path(config.pasta_fontes).glob("*.yaml")):
        fontes.append(_converter(yaml.safe_load(caminho.read_text(encoding="utf-8"))))
    return fontes
