"""Motor de demonstração: executa as receitas sem sair da máquina.

Serve para conhecer o sistema, treinar a equipe e rodar os testes sem
depender dos sites dos órgãos — inclusive o passo do captcha, que continua
pedindo resposta humana como no fluxo real.
"""

from __future__ import annotations

import asyncio
import base64
import random
import string
from datetime import date, timedelta

from ..modelos import SituacaoCertidao, TipoDesafio
from .extracao import analisar
from .pdf_simples import gerar
from .tipos import Contexto, ErroAutomacao, Receita, Resultado

ATRASO = float(0.2)  # simula a lentidão dos portais


def _captcha_svg(texto: str) -> str:
    letras = "".join(
        f'<text x="{12 + i * 26}" y="{40 + random.randint(-6, 6)}" font-size="30" '
        f'font-family="monospace" fill="#1b3a5c" transform="rotate({random.randint(-18, 18)} '
        f'{12 + i * 26} 40)">{c}</text>'
        for i, c in enumerate(texto)
    )
    ruido = "".join(
        f'<line x1="{random.randint(0, 170)}" y1="{random.randint(0, 60)}" '
        f'x2="{random.randint(0, 170)}" y2="{random.randint(0, 60)}" '
        f'stroke="#8aa" stroke-width="1"/>'
        for _ in range(7)
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="180" height="60">'
        '<rect width="180" height="60" fill="#eef3f8"/>' + ruido + letras + "</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


async def executar(receita: Receita, ctx: Contexto) -> Resultado:
    aguarda_anexo = receita.resultado == "anexo_manual"

    for passo in receita.passos:
        ctx.registrar("passo", f"{passo.acao} (simulado)")
        await asyncio.sleep(ATRASO)

        if passo.acao == "captcha_imagem":
            esperado = "".join(random.choices(string.ascii_lowercase, k=5))
            resposta = await ctx.perguntar(
                tipo=TipoDesafio.CAPTCHA_IMAGEM,
                instrucao=passo.get("instrucao") or "Digite os caracteres da imagem.",
                imagem=_captcha_svg(esperado),
                timeout=int(passo.get("timeout", 300)),
            )
            if resposta.strip().lower() != esperado:
                raise ErroAutomacao(
                    "Captcha incorreto (simulação). O sistema vai gerar uma nova imagem.",
                    repetir=True,
                )

        elif passo.acao in {"acao_manual", "login_gov_br", "captcha_interativo"}:
            aguarda_anexo = aguarda_anexo or passo.acao == "acao_manual"
            tipos = {
                "acao_manual": TipoDesafio.ACAO_MANUAL,
                "login_gov_br": TipoDesafio.LOGIN_GOV_BR,
                "captcha_interativo": TipoDesafio.CAPTCHA_INTERATIVO,
            }
            await ctx.perguntar(
                tipo=tipos[passo.acao],
                instrucao=ctx.aplicar(passo.get("instrucao")) or "Confirme para continuar.",
                timeout=int(passo.get("timeout", 600)),
            )

    if aguarda_anexo:
        return Resultado(
            sucesso=True,
            aguarda_anexo=True,
            mensagem="Simulação: conclua no site do órgão e anexe o PDF.",
        )

    hoje = date.today()
    validade = hoje + timedelta(days=179)
    numero = f"{random.randint(10_000_000, 99_999_999)}/{hoje.year}"
    documento = gerar(
        [
            f"Titular: {ctx.variaveis.get('nome', '')}",
            f"Inscricao: {ctx.variaveis.get('documento_formatado', '')}",
            f"Certidao n. {numero}",
            f"Expedicao: {hoje.strftime('%d/%m/%Y')}",
            f"Validade: {validade.strftime('%d/%m/%Y')}",
            "CERTIDAO NEGATIVA",
            "",
            "DOCUMENTO DE DEMONSTRACAO - SEM VALOR LEGAL",
        ],
        titulo=receita.nome,
    )
    dados = analisar(documento)
    return Resultado(
        sucesso=True,
        documento=documento,
        numero=dados["numero"] or numero,
        emitida_em=dados["emitida_em"] or hoje,
        valida_ate=dados["valida_ate"] or validade,
        situacao=dados["situacao"] or SituacaoCertidao.NEGATIVA,
        texto_extraido=dados["texto"],
        mensagem="Documento simulado (sem valor legal).",
    )
