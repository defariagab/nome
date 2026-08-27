"""Tipos compartilhados pelo motor de automação."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Awaitable, Callable, Protocol

from ..modelos import SituacaoCertidao, TipoDesafio


@dataclass(frozen=True)
class Passo:
    acao: str
    dados: dict[str, Any] = field(default_factory=dict)

    def get(self, chave: str, padrao: Any = None) -> Any:
        return self.dados.get(chave, padrao)


@dataclass(frozen=True)
class Receita:
    codigo: str
    nome: str
    url: str
    passos: list[Passo]
    resultado: str = "download"          # download | pagina_pdf | anexo_manual
    verificado_em: date | None = None

    @property
    def verificada(self) -> bool:
        return self.verificado_em is not None


class PerguntarHumano(Protocol):
    def __call__(
        self,
        *,
        tipo: TipoDesafio,
        instrucao: str,
        imagem: str | None = None,
        timeout: int = 300,
    ) -> Awaitable[str]:
        ...


@dataclass
class Contexto:
    """Tudo o que a execução de uma receita precisa saber e pode fazer."""

    solicitacao_id: int
    variaveis: dict[str, str]
    perguntar: PerguntarHumano
    registrar: Callable[[str, str], None]
    pasta_sessao: str | None = None
    visivel: bool = True

    def aplicar(self, texto: str | None) -> str:
        """Substitui {variaveis} de um valor da receita."""
        if not texto:
            return ""
        resultado = texto
        for chave, valor in self.variaveis.items():
            resultado = resultado.replace("{" + chave + "}", valor or "")
        return resultado


class ErroAutomacao(RuntimeError):
    """Falha esperada e explicável da automação (mensagem vai para o usuário)."""

    def __init__(self, mensagem: str, *, repetir: bool = False):
        super().__init__(mensagem)
        self.repetir = repetir


@dataclass
class Resultado:
    sucesso: bool
    mensagem: str = ""
    documento: bytes | None = None
    extensao: str = "pdf"
    numero: str | None = None
    codigo_verificacao: str | None = None
    emitida_em: date | None = None
    valida_ate: date | None = None
    situacao: SituacaoCertidao = SituacaoCertidao.NAO_IDENTIFICADA
    aguarda_anexo: bool = False
    texto_extraido: str = ""
