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

    @property
    def opcional(self) -> bool:
        """Passo que pode não existir na página (banner de cookies, aviso...)."""
        return bool(self.dados.get("opcional"))

    def se_aplica(self, variaveis: dict[str, str]) -> bool:
        """Avalia `quando:`, que liga o passo a uma variável do titular.

        `quando: cnpj` roda só para pessoa jurídica; `quando: "!cnpj"` só para
        pessoa física. É o suficiente para os sites que separam os dois campos.
        """
        condicao = str(self.dados.get("quando", "")).strip()
        if not condicao:
            return True
        negada = condicao.startswith("!")
        nome = condicao.lstrip("!").strip()
        preenchida = bool((variaveis.get(nome) or "").strip())
        return not preenchida if negada else preenchida


@dataclass(frozen=True)
class Fonte:
    codigo: str
    nome: str
    url: str
    passos: list[Passo]
    #: "navegador" opera o site; "api" chama um serviço contratado
    tipo: str = "navegador"
    #: configuração da chamada, quando `tipo: api`
    api: dict = field(default_factory=dict)
    resultado: str = "download"          # download | pagina_pdf | anexo_manual
    verificado_em: date | None = None
    #: o que fazer quando um passo não encontra o que esperava no site:
    #: "pedir_anexo" deixa o navegador aberto na página certa e pede que a
    #: pessoa conclua e anexe o PDF, em vez de simplesmente falhar
    ao_falhar: str = "falhar"
    #: perfil de navegador reaproveitado entre emissões (ex.: "govbr"), para
    #: que o login feito uma vez sirva para as próximas certidões
    perfil: str | None = None
    #: captchas de letras podem rodar em paralelo — o usuário responde vários
    #: seguidos. Widget interativo e sessão logada exigem uma janela por vez.
    _paralelizavel: bool = True

    @property
    def verificada(self) -> bool:
        return self.verificado_em is not None

    #: passos que precisam do navegador controlado pelo sistema
    ACOES_COM_NAVEGADOR = frozenset({
        "abrir", "preencher", "selecionar", "clicar", "esperar", "captcha_imagem",
        "captcha_interativo", "exigir_texto", "aguardar_download", "salvar_pagina_pdf",
        "login_gov_br",
    })

    @property
    def exige_navegador(self) -> bool:
        """Uma fonte que só abre o navegador do usuário não precisa do nosso."""
        if self.tipo == "api":
            return False
        return any(passo.acao in self.ACOES_COM_NAVEGADOR for passo in self.passos)

    @property
    def paralelizavel(self) -> bool:
        if self.perfil:
            return False
        return self._paralelizavel and not any(
            passo.acao in {"captcha_interativo", "login_gov_br", "acao_manual",
                           "abrir_no_navegador"}
            for passo in self.passos
        )


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
    """Tudo o que a execução de uma fonte precisa saber e pode fazer."""

    solicitacao_id: int
    variaveis: dict[str, str]
    perguntar: PerguntarHumano
    registrar: Callable[[str, str], None]
    pasta_sessao: str | None = None
    visivel: bool = True
    #: credenciais já decifradas, por rótulo (usadas pelas fontes de API)
    segredos: dict[str, str] = field(default_factory=dict)

    def aplicar(self, texto: str | None) -> str:
        """Substitui {variaveis} de um valor da fonte."""
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
    #: custo cobrado pela emissão, quando a fonte é uma API paga
    custo: float = 0.0
