"""Fila de pedidos de ajuda humana (captcha, login gov.br, ação manual).

A automação para, publica o desafio na tela e espera a resposta da pessoa.
Nenhum captcha é quebrado ou contornado pelo sistema: quem responde é o
usuário, exatamente como faria no site do órgão.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

from ..banco import sessao
from ..modelos import Desafio, EstadoDesafio, TipoDesafio, agora

INTERVALO = 1.0  # segundos entre consultas ao banco


class DesafioExpirado(RuntimeError):
    pass


def criar(solicitacao_id: int, tipo: TipoDesafio, instrucao: str,
          imagem: str | None = None, timeout: int = 300) -> int:
    with sessao() as s:
        desafio = Desafio(
            solicitacao_id=solicitacao_id,
            tipo=tipo,
            instrucao=instrucao,
            imagem=imagem,
            expira_em=agora() + timedelta(seconds=timeout),
        )
        s.add(desafio)
        s.flush()
        return desafio.id


def responder(desafio_id: int, resposta: str) -> bool:
    with sessao() as s:
        desafio = s.get(Desafio, desafio_id)
        if not desafio or desafio.estado is not EstadoDesafio.ABERTO:
            return False
        desafio.resposta = resposta
        desafio.estado = EstadoDesafio.RESPONDIDO
        desafio.respondido_em = agora()
        return True


def cancelar_abertos(solicitacao_id: int) -> None:
    with sessao() as s:
        for desafio in s.scalars(
            select(Desafio).where(
                Desafio.solicitacao_id == solicitacao_id,
                Desafio.estado == EstadoDesafio.ABERTO,
            )
        ):
            desafio.estado = EstadoDesafio.CANCELADO


async def perguntar(
    solicitacao_id: int,
    *,
    tipo: TipoDesafio,
    instrucao: str,
    imagem: str | None = None,
    timeout: int = 300,
) -> str:
    """Publica o desafio e aguarda a resposta do usuário."""
    desafio_id = criar(solicitacao_id, tipo, instrucao, imagem, timeout)
    limite = agora() + timedelta(seconds=timeout)
    while True:
        await asyncio.sleep(INTERVALO)
        with sessao() as s:
            desafio = s.get(Desafio, desafio_id)
            if desafio is None or desafio.estado is EstadoDesafio.CANCELADO:
                raise DesafioExpirado("O pedido de ajuda foi cancelado.")
            if desafio.estado is EstadoDesafio.RESPONDIDO:
                return desafio.resposta or ""
            if agora() > limite:
                desafio.estado = EstadoDesafio.EXPIRADO
                raise DesafioExpirado(
                    "Ninguém respondeu ao pedido de ajuda a tempo. A solicitação pode ser reenviada."
                )
