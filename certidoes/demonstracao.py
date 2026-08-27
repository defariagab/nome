"""Dados de demonstração: um escritório fictício com situações variadas.

Útil para conhecer o sistema, treinar a equipe e apresentar a ferramenta
sem expor dados reais de clientes.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from . import servicos
from .automacao.pdf_simples import gerar
from .banco import sessao
from .modelos import EstadoSolicitacao, SituacaoCertidao, TipoCertidao

TITULARES = [
    ("Construtora Horizonte Ltda", "11.222.333/0001-81", "SP", "São Paulo"),
    ("Transportes Ipê S.A.", "34.028.316/0001-03", "MG", "Belo Horizonte"),
    ("Maria Alves de Souza", "529.982.247-25", "SP", "Campinas"),
]

#: (código do tipo, dias desde a emissão, situação) — desenha o painel de exemplo
SITUACOES = {
    "11222333000181": [
        ("cndt", 20, SituacaoCertidao.NEGATIVA),
        ("fgts_crf", 26, SituacaoCertidao.NEGATIVA),
        ("rfb_pgfn_conjunta", 200, SituacaoCertidao.NEGATIVA),   # já vencida
        ("tj_falencia_concordata", None, None),                  # nunca emitida
    ],
    "34028316000103": [
        ("cndt", 100, SituacaoCertidao.POSITIVA),                # com débitos
        ("fgts_crf", 2, SituacaoCertidao.NEGATIVA),
    ],
    "52998224725": [
        ("cndt", 5, SituacaoCertidao.NEGATIVA),
        ("rfb_pgfn_conjunta", 170, SituacaoCertidao.POSITIVA_COM_EFEITO_NEGATIVO),
    ],
}


def povoar() -> int:
    """Cria os titulares e o histórico de exemplo. Devolve quantos foram criados."""
    criados = 0
    with sessao() as s:
        for nome, documento, uf, municipio in TITULARES:
            digitos = "".join(c for c in documento if c.isdigit())
            if s.scalar(select(servicos.Titular).where(servicos.Titular.documento == digitos)):
                continue
            titular = servicos.salvar_titular(
                s, {"nome": nome, "documento": documento, "uf": uf, "municipio": municipio}
            )
            s.flush()
            criados += 1

            planejadas = SITUACOES.get(digitos, [])
            tipos = {}
            for codigo, _dias, _situacao in planejadas:
                tipo = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == codigo))
                if tipo:
                    tipos[codigo] = tipo
            servicos.definir_monitoramentos(s, titular.id, [t.id for t in tipos.values()])

            for codigo, dias, situacao in planejadas:
                if dias is None or codigo not in tipos:
                    continue
                tipo = tipos[codigo]
                emissao = date.today() - timedelta(days=dias)
                validade = emissao + timedelta(days=tipo.validade_dias - 1)
                solicitacao = servicos.solicitar(s, titular.id, tipo.id)
                solicitacao.estado = EstadoSolicitacao.CONCLUIDA
                pdf = gerar(
                    [
                        f"Titular: {nome}",
                        f"Inscricao: {documento}",
                        f"Expedicao: {emissao.strftime('%d/%m/%Y')}",
                        f"Validade: {validade.strftime('%d/%m/%Y')}",
                        situacao.value.replace("_", " ").upper(),
                        "",
                        "DOCUMENTO DE DEMONSTRACAO - SEM VALOR LEGAL",
                    ],
                    titulo=tipo.nome,
                )
                servicos.guardar_resultado(
                    s, solicitacao, documento=pdf, emitida_em=emissao,
                    valida_ate=validade, situacao=situacao,
                )
    return criados
