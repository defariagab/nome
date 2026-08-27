"""Percurso completo: pedido na fila, captcha respondido, certidão arquivada."""

import asyncio
import base64
import re
from datetime import date

from sqlalchemy import select

from certidoes import servicos
from certidoes.automacao import desafios
from certidoes.banco import sessao
from certidoes.fila import Fila
from certidoes.modelos import (
    Certidao, Desafio, EstadoDesafio, EstadoSolicitacao, Solicitacao, TipoCertidao,
)


def tipo_por_codigo(s, codigo):
    return s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == codigo))


def ler_captcha(imagem: str) -> str:
    """Lê os caracteres do captcha simulado — o que uma pessoa faria olhando."""
    svg = base64.b64decode(imagem.split(",", 1)[1]).decode()
    return "".join(re.findall(r'font-family="monospace"[^>]*>(\w)</text>', svg))


async def _responder_desafios(erros_primeiro: int = 0):
    """Responde os pedidos de ajuda que forem aparecendo."""
    respondidos = 0
    for _ in range(600):
        await asyncio.sleep(0.05)
        with sessao() as s:
            desafio = s.scalar(
                select(Desafio).where(Desafio.estado == EstadoDesafio.ABERTO).order_by(Desafio.id)
            )
            if desafio is None:
                continue
            dados = (desafio.id, desafio.imagem)
        resposta = "errado" if respondidos < erros_primeiro else (
            ler_captcha(dados[1]) if dados[1] else "ok"
        )
        desafios.responder(dados[0], resposta)
        respondidos += 1
    return respondidos


async def _executar(solicitacao_id: int, erros: int = 0):
    fila = Fila(motor="simulador")
    ajudante = asyncio.create_task(_responder_desafios(erros))
    try:
        await asyncio.wait_for(fila._processar(solicitacao_id), timeout=30)
    finally:
        ajudante.cancel()


def _preparar(codigo: str) -> int:
    with sessao() as s:
        titular = servicos.salvar_titular(
            s, {"nome": "Empresa Exemplo Ltda", "documento": "11222333000181", "uf": "SP"}
        )
        tipo = tipo_por_codigo(s, codigo)
        servicos.definir_monitoramentos(s, titular.id, [tipo.id])
        s.flush()
        return servicos.solicitar(s, titular.id, tipo.id).id


def test_emite_arquiva_e_calcula_validade():
    solicitacao_id = _preparar("cndt")
    asyncio.run(_executar(solicitacao_id))

    with sessao() as s:
        solicitacao = s.get(Solicitacao, solicitacao_id)
        assert solicitacao.estado is EstadoSolicitacao.CONCLUIDA
        certidao = s.get(Certidao, solicitacao.certidao_id)
        assert certidao is not None
        assert certidao.valida_ate > date.today()
        assert certidao.arquivo and certidao.arquivo_hash
        assert any(r["tipo"] == "concluido" for r in solicitacao.registro)


def test_captcha_errado_gera_nova_tentativa():
    solicitacao_id = _preparar("cndt")
    asyncio.run(_executar(solicitacao_id, erros=1))

    with sessao() as s:
        solicitacao = s.get(Solicitacao, solicitacao_id)
        assert solicitacao.estado is EstadoSolicitacao.CONCLUIDA
        assert any("Captcha incorreto" in r["mensagem"] for r in solicitacao.registro)


def test_arquivo_fica_legivel_no_acervo():
    solicitacao_id = _preparar("cndt")
    asyncio.run(_executar(solicitacao_id))

    from certidoes import arquivos

    with sessao() as s:
        certidao = s.scalar(select(Certidao))
        conteudo = arquivos.ler(certidao.arquivo)
    assert conteudo.startswith(b"%PDF")


def test_sem_automacao_o_sistema_pede_o_anexo():
    # tipo sem receita: o sistema abre o site do órgão e pede o PDF
    solicitacao_id = _preparar("tj_falencia_concordata")
    asyncio.run(_executar(solicitacao_id))

    with sessao() as s:
        solicitacao = s.get(Solicitacao, solicitacao_id)
        assert solicitacao.estado is EstadoSolicitacao.AGUARDANDO_ANEXO

    from certidoes.automacao.pdf_simples import gerar

    pdf = gerar(["Certidao n. 55/2026", "Validade: 30/11/2026", "CERTIDAO NEGATIVA"], "CND")
    with sessao() as s:
        certidao = servicos.anexar_documento(s, solicitacao_id, pdf)
        assert certidao.valida_ate == date(2026, 11, 30)
        assert certidao.origem == "upload"
        assert s.get(Solicitacao, solicitacao_id).estado is EstadoSolicitacao.CONCLUIDA


def test_desafio_cancelado_encerra_a_solicitacao():
    solicitacao_id = _preparar("cndt")

    async def cenario():
        fila = Fila(motor="simulador")
        tarefa = asyncio.create_task(fila._processar(solicitacao_id))
        for _ in range(200):
            await asyncio.sleep(0.05)
            with sessao() as s:
                if s.scalar(select(Desafio).where(Desafio.estado == EstadoDesafio.ABERTO)):
                    break
        desafios.cancelar_abertos(solicitacao_id)
        await asyncio.wait_for(tarefa, timeout=15)

    asyncio.run(cenario())
    with sessao() as s:
        assert s.get(Solicitacao, solicitacao_id).estado is EstadoSolicitacao.FALHOU
