"""Dossiê de regularidade: um único PDF com todas as certidões vigentes.

É o que a habilitação de uma licitação pede — e o que hoje se monta à mão,
juntando arquivo por arquivo. Traz uma folha de rosto que lista o que está
dentro e até quando cada documento vale.
"""

from __future__ import annotations

import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import arquivos
from .automacao.pdf_simples import gerar
from .documento import formatar
from .modelos import Certidao, TipoCertidao, Titular
from .validade import Status, avaliar


class SemCertidoes(RuntimeError):
    """Não há documento vigente para montar o dossiê."""


def certidoes_do_dossie(s: Session, titular_id: int, hoje: date | None = None) -> list[Certidao]:
    """As certidões que comprovam regularidade hoje, uma por tipo."""
    hoje = hoje or date.today()
    consulta = (
        select(Certidao)
        .where(Certidao.titular_id == titular_id, Certidao.substituida.is_(False))
        .order_by(Certidao.tipo_certidao_id, Certidao.valida_ate.desc())
    )
    por_tipo: dict[int, Certidao] = {}
    for certidao in s.scalars(consulta):
        if certidao.tipo_certidao_id in por_tipo or not certidao.arquivo:
            continue
        vigencia = avaliar(certidao.valida_ate, hoje=hoje, regular=certidao.situacao.regular)
        if vigencia.status in {Status.VIGENTE, Status.VENCE_EM_BREVE}:
            por_tipo[certidao.tipo_certidao_id] = certidao
    return list(por_tipo.values())


def _folha_de_rosto(s: Session, titular: Titular, certidoes: list[Certidao], hoje: date) -> bytes:
    linhas = [
        f"Titular: {titular.nome}",
        f"Inscricao: {formatar(titular.documento)}",
        f"Emitido em: {hoje.strftime('%d/%m/%Y')}",
        "",
        "Documentos reunidos neste dossie:",
        "",
    ]
    for certidao in certidoes:
        tipo = s.get(TipoCertidao, certidao.tipo_certidao_id)
        sigla = tipo.sigla or tipo.codigo.upper()
        linhas.append(
            f"- {sigla}: {tipo.nome[:60]}"
        )
        linhas.append(
            f"    orgao: {tipo.orgao[:60]}"
        )
        linhas.append(
            f"    emitida em {certidao.emitida_em.strftime('%d/%m/%Y')}, "
            f"valida ate {certidao.valida_ate.strftime('%d/%m/%Y')}"
            + (f", n. {certidao.numero}" if certidao.numero else "")
        )
        linhas.append("")
    linhas.append("As certidoes originais seguem nas paginas a seguir.")
    return gerar(linhas, titulo="DOSSIE DE REGULARIDADE")


def montar(s: Session, titular_id: int, hoje: date | None = None) -> tuple[bytes, str]:
    """Devolve ``(pdf, nome_do_arquivo)`` com a folha de rosto e as certidões."""
    from pypdf import PdfReader, PdfWriter

    titular = s.get(Titular, titular_id)
    if titular is None:
        raise SemCertidoes("Titular não encontrado.")
    hoje = hoje or date.today()
    certidoes = certidoes_do_dossie(s, titular_id, hoje)
    if not certidoes:
        raise SemCertidoes(
            "Este titular não tem nenhuma certidão vigente arquivada. Emita ou anexe as "
            "certidões antes de montar o dossiê."
        )

    escritor = PdfWriter()
    for pagina in PdfReader(io.BytesIO(_folha_de_rosto(s, titular, certidoes, hoje))).pages:
        escritor.add_page(pagina)

    for certidao in certidoes:
        try:
            conteudo = arquivos.ler(certidao.arquivo)
            for pagina in PdfReader(io.BytesIO(conteudo)).pages:
                escritor.add_page(pagina)
        except Exception:
            # Um arquivo ilegível não pode impedir o dossiê inteiro: a folha de
            # rosto continua listando o documento, e o problema aparece no acervo.
            continue

    saida = io.BytesIO()
    escritor.write(saida)
    nome = f"dossie_{titular.documento}_{hoje.isoformat()}.pdf"
    return saida.getvalue(), nome
