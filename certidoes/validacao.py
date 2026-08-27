"""Um documento só entra no acervo se for mesmo uma certidão.

Sites de órgão respondem com página de erro, aviso de instabilidade e tela de
manutenção — tudo com aparência de resposta normal e status 200. Arquivar isso
como certidão é pior do que falhar: o painel mostra verde, o dossiê leva a
página errada, e o problema só aparece na mesa do fiscal.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .modelos import SituacaoCertidao

#: frases que os órgãos usam para dizer que não conseguiram responder
INDISPONIBILIDADE = [
    "nao foi possivel verificar",
    "nao foi possivel emitir",
    "nao foi possivel processar",
    "solicitamos tentar mais tarde",
    "tente novamente mais tarde",
    "comparecer a uma das agencias",
    "sistema indisponivel",
    "servico indisponivel",
    "em manutencao",
    "erro ao processar",
    "ocorreu um erro",
    "acesso foi bloqueado",
    "tempo de sessao expirou",
    "sessao expirada",
]


@dataclass(frozen=True)
class Veredito:
    aceitavel: bool
    motivo: str = ""

    def __bool__(self) -> bool:
        return self.aceitavel


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    ).lower()


def frase_de_indisponibilidade(texto: str) -> str:
    """Devolve a frase de erro encontrada no documento, se houver."""
    plano = re.sub(r"\s+", " ", _sem_acento(texto))
    for frase in INDISPONIBILIDADE:
        if frase in plano:
            return frase
    return ""


def avaliar(
    texto: str,
    *,
    situacao: SituacaoCertidao = SituacaoCertidao.NAO_IDENTIFICADA,
    valida_ate=None,
    numero: str | None = None,
) -> Veredito:
    """Diz se o que voltou do órgão pode ser arquivado como certidão."""
    if not (texto or "").strip():
        return Veredito(
            False,
            "O documento veio vazio ou ilegível — não dá para conferir se é mesmo a certidão.",
        )

    if frase := frase_de_indisponibilidade(texto):
        return Veredito(
            False,
            "O órgão não emitiu a certidão: a resposta traz um aviso de indisponibilidade "
            f'("{frase}"). Vale tentar de novo mais tarde.',
        )

    # Sem situação reconhecida, sem validade e sem número, não há como afirmar
    # que isto é uma certidão — e afirmar por afirmar é o erro que se quer evitar.
    if situacao is SituacaoCertidao.NAO_IDENTIFICADA and not valida_ate and not numero:
        return Veredito(
            False,
            "O documento não parece uma certidão: não traz situação, validade nem número. "
            "Confira a página que o órgão apresentou.",
        )

    return Veredito(True)
