"""Renovação automática: o sistema pede a certidão antes de ela vencer."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import select

from . import servicos
from .banco import sessao
from .modelos import EstadoSolicitacao, Monitoramento, Solicitacao, Titular, agora
from .validade import Status, avaliar

log = logging.getLogger("certidoes.agenda")

#: intervalo entre as varreduras (a renovação não tem pressa de minutos)
INTERVALO_HORAS = 6
#: depois de uma falha, espera antes de tentar de novo sozinho
ESPERA_APOS_FALHA_HORAS = 12


def _falhou_recentemente(s, titular_id: int, tipo_id: int) -> bool:
    limite = agora() - timedelta(hours=ESPERA_APOS_FALHA_HORAS)
    return bool(s.scalar(
        select(Solicitacao.id).where(
            Solicitacao.titular_id == titular_id,
            Solicitacao.tipo_certidao_id == tipo_id,
            Solicitacao.estado == EstadoSolicitacao.FALHOU,
            Solicitacao.concluida_em >= limite,
        ).limit(1)
    ))


def pendentes_de_renovacao(s, hoje: date | None = None) -> list[Monitoramento]:
    """Monitoramentos cuja certidão já venceu, vai vencer ou nunca foi emitida."""
    encontrados = []
    consulta = (
        select(Monitoramento).join(Titular)
        .where(Monitoramento.ativo, Monitoramento.renovar_automaticamente, Titular.ativo)
    )
    for monitoramento in s.scalars(consulta):
        certidao = servicos.certidao_vigente(s, monitoramento.titular_id, monitoramento.tipo_certidao_id)
        vigencia = avaliar(
            certidao.valida_ate if certidao else None,
            hoje=hoje,
            dias_antecedencia=monitoramento.dias_antecedencia,
            regular=certidao.situacao.regular if certidao else True,
        )
        # Certidão positiva não se resolve reemitindo: o débito precisa ser tratado.
        if vigencia.status is Status.IRREGULAR:
            continue
        if vigencia.precisa_renovar:
            encontrados.append(monitoramento)
    return encontrados


def varrer(hoje: date | None = None) -> list[int]:
    """Cria as solicitações de renovação necessárias. Devolve os ids criados."""
    criadas: list[int] = []
    with sessao() as s:
        for monitoramento in pendentes_de_renovacao(s, hoje):
            titular_id, tipo_id = monitoramento.titular_id, monitoramento.tipo_certidao_id
            # Já está na fila ou já falhou há pouco: não adianta pedir de novo.
            if servicos.solicitacao_em_andamento(s, titular_id, tipo_id):
                continue
            if _falhou_recentemente(s, titular_id, tipo_id):
                continue
            criadas.append(servicos.solicitar(s, titular_id, tipo_id, origem="renovacao").id)
    if criadas:
        log.info("Renovação automática criou %s solicitações", len(criadas))
    return criadas


async def rodar_periodicamente(intervalo_horas: int = INTERVALO_HORAS) -> None:
    while True:
        try:
            varrer()
        except Exception:  # pragma: no cover
            log.exception("Falha na varredura de renovação")
        await asyncio.sleep(intervalo_horas * 3600)
