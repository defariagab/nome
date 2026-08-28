"""Seleção do motor de execução e política de repetição.

Quando o site recusa a resposta do captcha, não é falha da automação: é o
caso normal de errar a leitura da imagem. Aqui a fonte é refeita do zero,
com uma imagem nova, algumas vezes antes de desistir.
"""

from __future__ import annotations

from ..config import config
from .tipos import Contexto, ErroAutomacao, Fonte, Resultado

TENTATIVAS_COM_REPETICAO = 3


async def _uma_tentativa(fonte: Fonte, ctx: Contexto, escolhido: str) -> Resultado:
    if fonte.tipo == "api" and escolhido != "simulador":
        from . import motor_api

        rotulo = (fonte.api or {}).get("credencial", fonte.codigo)
        return await motor_api.executar(fonte, ctx, token=ctx.segredos.get(rotulo))
    if escolhido == "simulador":
        from . import motor_simulador

        return await motor_simulador.executar(fonte, ctx)
    from . import motor_navegador

    return await motor_navegador.executar(fonte, ctx)


async def executar(fonte: Fonte, ctx: Contexto, motor: str | None = None) -> Resultado:
    escolhido = motor or config.motor
    for tentativa in range(1, TENTATIVAS_COM_REPETICAO + 1):
        try:
            return await _uma_tentativa(fonte, ctx, escolhido)
        except ErroAutomacao as erro:
            if not erro.repetir or tentativa == TENTATIVAS_COM_REPETICAO:
                raise
            ctx.registrar("repetindo", f"{erro} (tentativa {tentativa})")
    raise ErroAutomacao("Falha desconhecida na automação.")  # pragma: no cover
