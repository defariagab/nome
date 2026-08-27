"""Automação: fontes declarativas executadas por um navegador de verdade."""

from .fontes import carregar_fonte, listar_fontes
from .tipos import Contexto, Passo, Fonte, Resultado

__all__ = ["Contexto", "Passo", "Fonte", "Resultado", "carregar_fonte", "listar_fontes"]
