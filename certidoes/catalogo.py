"""Carga do catálogo de tipos de certidão para o banco."""

from __future__ import annotations

import yaml
from sqlalchemy import select

from .banco import sessao
from .config import config
from .modelos import Captcha, Esfera, ModoObtencao, TipoCertidao

#: campos que o sistema atualiza a cada carga; os demais o usuário pode editar
#: pela tela sem que a próxima atualização do catálogo desfaça a alteração.
CAMPOS_DO_CATALOGO = {
    "nome", "sigla", "orgao", "esfera", "aplica_pf", "aplica_pj",
    "requer_gov_br", "requer_certificado", "captcha", "modo", "receita",
    "verificado_em", "observacoes",
}


def _converter(bruto: dict) -> dict:
    dados = dict(bruto)
    dados["esfera"] = Esfera(dados.get("esfera", "federal"))
    dados["captcha"] = Captcha(dados.get("captcha", "desconhecido"))
    dados["modo"] = ModoObtencao(dados.get("modo", "manual"))
    return dados


def carregar(caminho=None) -> int:
    """Insere os tipos novos e atualiza os campos técnicos dos já existentes."""
    arquivo = caminho or (config.pasta_catalogo / "catalogo.yaml")
    itens = yaml.safe_load(arquivo.read_text(encoding="utf-8")) or []
    novos = 0
    with sessao() as s:
        for bruto in itens:
            dados = _converter(bruto)
            existente = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == dados["codigo"]))
            if existente is None:
                s.add(TipoCertidao(**dados))
                novos += 1
                continue
            for campo, valor in dados.items():
                if campo in CAMPOS_DO_CATALOGO:
                    setattr(existente, campo, valor)
            if not existente.url:
                existente.url = dados.get("url") or ""
    return novos
