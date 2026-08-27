"""Carregamento das receitas declarativas (YAML)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..config import config
from .tipos import Passo, Receita


def _converter(bruto: dict) -> Receita:
    passos = [Passo(acao=p["acao"], dados={k: v for k, v in p.items() if k != "acao"})
              for p in bruto.get("passos", [])]
    return Receita(
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
def carregar_receita(codigo: str) -> Receita | None:
    caminho = config.pasta_receitas / f"{codigo}.yaml"
    if not caminho.exists():
        return None
    return _converter(yaml.safe_load(caminho.read_text(encoding="utf-8")))


def listar_receitas() -> list[Receita]:
    receitas = []
    for caminho in sorted(Path(config.pasta_receitas).glob("*.yaml")):
        receitas.append(_converter(yaml.safe_load(caminho.read_text(encoding="utf-8"))))
    return receitas
