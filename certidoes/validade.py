"""Regras de vigência: o coração da gestão de certidões."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class Status(str, Enum):
    AUSENTE = "ausente"          # nunca foi emitida
    VIGENTE = "vigente"
    VENCE_EM_BREVE = "vence_em_breve"
    VENCIDA = "vencida"
    IRREGULAR = "irregular"      # emitida, porém positiva (com débitos)

    @property
    def rotulo(self) -> str:
        return {
            Status.AUSENTE: "Não emitida",
            Status.VIGENTE: "Vigente",
            Status.VENCE_EM_BREVE: "Vence em breve",
            Status.VENCIDA: "Vencida",
            Status.IRREGULAR: "Positiva (com débitos)",
        }[self]

    @property
    def prioridade(self) -> int:
        """Ordem de urgência para o painel (menor = mais urgente)."""
        return [Status.IRREGULAR, Status.VENCIDA, Status.AUSENTE,
                Status.VENCE_EM_BREVE, Status.VIGENTE].index(self)


@dataclass(frozen=True)
class Vigencia:
    status: Status
    dias_restantes: int | None
    valida_ate: date | None

    @property
    def precisa_renovar(self) -> bool:
        return self.status in {Status.AUSENTE, Status.VENCIDA, Status.VENCE_EM_BREVE, Status.IRREGULAR}


def calcular_validade(emitida_em: date, validade_dias: int) -> date:
    """Último dia de validade. Uma certidão de 180 dias emitida hoje vale
    até hoje + 180 dias (o dia da emissão conta como primeiro dia)."""
    if validade_dias <= 0:
        raise ValueError("validade_dias deve ser positivo")
    return emitida_em + timedelta(days=validade_dias - 1)


def avaliar(
    valida_ate: date | None,
    *,
    hoje: date | None = None,
    dias_antecedencia: int = 15,
    regular: bool = True,
) -> Vigencia:
    """Classifica a situação de uma certidão.

    ``regular`` é False quando a certidão saiu positiva (com débitos): mesmo
    dentro do prazo ela não serve para comprovar regularidade.
    """
    hoje = hoje or date.today()
    if valida_ate is None:
        return Vigencia(Status.AUSENTE, None, None)
    dias = (valida_ate - hoje).days
    if dias < 0:
        return Vigencia(Status.VENCIDA, dias, valida_ate)
    if not regular:
        return Vigencia(Status.IRREGULAR, dias, valida_ate)
    if dias <= dias_antecedencia:
        return Vigencia(Status.VENCE_EM_BREVE, dias, valida_ate)
    return Vigencia(Status.VIGENTE, dias, valida_ate)


def data_de_renovacao(valida_ate: date, dias_antecedencia: int = 15) -> date:
    """Quando a renovação automática deve disparar."""
    return valida_ate - timedelta(days=dias_antecedencia)
