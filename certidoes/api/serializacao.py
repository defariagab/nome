"""Conversão dos registros para o formato que a tela consome."""

from __future__ import annotations

from ..documento import formatar
from ..modelos import Certidao, Desafio, Evento, Solicitacao, TipoCertidao, Titular


def titular(t: Titular, monitorados: list[int] | None = None) -> dict:
    return {
        "id": t.id,
        "nome": t.nome,
        "tipo": t.tipo.value,
        "documento": t.documento,
        "documento_formatado": formatar(t.documento),
        "inscricao_estadual": t.inscricao_estadual,
        "uf": t.uf,
        "municipio": t.municipio,
        "codigo_ibge": t.codigo_ibge,
        "email": t.email,
        "observacoes": t.observacoes,
        "ativo": t.ativo,
        "monitoramentos": monitorados or [],
    }


def tipo(tc: TipoCertidao) -> dict:
    return {
        "id": tc.id,
        "codigo": tc.codigo,
        "nome": tc.nome,
        "sigla": tc.sigla,
        "orgao": tc.orgao,
        "esfera": tc.esfera.value,
        "aplica_pf": tc.aplica_pf,
        "aplica_pj": tc.aplica_pj,
        "validade_dias": tc.validade_dias,
        "requer_gov_br": tc.requer_gov_br,
        "requer_certificado": tc.requer_certificado,
        "captcha": tc.captcha.value,
        "modo": tc.modo.value,
        "receita": tc.receita,
        "url": tc.url,
        "verificado_em": tc.verificado_em.isoformat() if tc.verificado_em else None,
        "observacoes": tc.observacoes,
        "ativo": tc.ativo,
    }


def solicitacao(s: Solicitacao, nome_titular: str = "", nome_tipo: str = "") -> dict:
    return {
        "id": s.id,
        "titular_id": s.titular_id,
        "titular": nome_titular,
        "tipo_id": s.tipo_certidao_id,
        "tipo": nome_tipo,
        "estado": s.estado.value,
        "origem": s.origem,
        "tentativas": s.tentativas,
        "mensagem": s.mensagem,
        "diagnostico": s.diagnostico,
        "registro": s.registro or [],
        "certidao_id": s.certidao_id,
        "criado_em": s.criado_em.isoformat() if s.criado_em else None,
        "concluida_em": s.concluida_em.isoformat() if s.concluida_em else None,
    }


def certidao(c: Certidao, nome_titular: str = "", nome_tipo: str = "") -> dict:
    return {
        "id": c.id,
        "titular_id": c.titular_id,
        "titular": nome_titular,
        "tipo_id": c.tipo_certidao_id,
        "tipo": nome_tipo,
        "numero": c.numero,
        "codigo_verificacao": c.codigo_verificacao,
        "emitida_em": c.emitida_em.isoformat(),
        "valida_ate": c.valida_ate.isoformat(),
        "situacao": c.situacao.value,
        "origem": c.origem,
        "substituida": c.substituida,
        "tem_arquivo": bool(c.arquivo),
    }


def desafio(d: Desafio, nome_titular: str = "", nome_tipo: str = "") -> dict:
    return {
        "id": d.id,
        "solicitacao_id": d.solicitacao_id,
        "tipo": d.tipo.value,
        "instrucao": d.instrucao,
        "imagem": d.imagem,
        "titular": nome_titular,
        "certidao": nome_tipo,
        "expira_em": d.expira_em.isoformat() if d.expira_em else None,
    }


def evento(e: Evento) -> dict:
    return {
        "id": e.id,
        "entidade": e.entidade,
        "entidade_id": e.entidade_id,
        "tipo": e.tipo,
        "mensagem": e.mensagem,
        "criado_em": e.criado_em.isoformat(),
    }
