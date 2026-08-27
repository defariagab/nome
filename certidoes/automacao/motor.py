"""Seleção do motor de execução e política de repetição.

Quando o site recusa a resposta do captcha, não é falha da automação: é o
caso normal de errar a leitura da imagem. Aqui a receita é refeita do zero,
com uma imagem nova, algumas vezes antes de desistir.
"""

from __future__ import annotations

from ..config import config
from .tipos import Contexto, ErroAutomacao, Receita, Resultado

TENTATIVAS_COM_REPETICAO = 3


async def _uma_tentativa(receita: Receita, ctx: Contexto, escolhido: str) -> Resultado:
    if escolhido == "simulador":
        from . import motor_simulador

        return await motor_simulador.executar(receita, ctx)
    from . import motor_navegador

    return await motor_navegador.executar(receita, ctx)


async def executar(receita: Receita, ctx: Contexto, motor: str | None = None) -> Resultado:
    escolhido = motor or config.motor
    for tentativa in range(1, TENTATIVAS_COM_REPETICAO + 1):
        try:
            return await _uma_tentativa(receita, ctx, escolhido)
        except ErroAutomacao as erro:
            if not erro.repetir or tentativa == TENTATIVAS_COM_REPETICAO:
                raise
            ctx.registrar("repetindo", f"{erro} (tentativa {tentativa})")
    raise ErroAutomacao("Falha desconhecida na automação.")  # pragma: no cover
