"""Automação: receitas declarativas executadas por um navegador de verdade."""

from .receitas import carregar_receita, listar_receitas
from .tipos import Contexto, Passo, Receita, Resultado

__all__ = ["Contexto", "Passo", "Receita", "Resultado", "carregar_receita", "listar_receitas"]
