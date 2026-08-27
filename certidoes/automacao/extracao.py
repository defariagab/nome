"""Leitura do documento emitido: datas, número e situação.

O que o próprio documento diz vale mais do que o padrão do catálogo — é ele
que o órgão fiscalizador vai olhar.
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, datetime

from ..modelos import SituacaoCertidao

_DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
#: padrões de validade, do mais específico ao mais genérico
_VALIDADES = [
    re.compile(r"v[aá]lid[ao]\s+at[eé]\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE),
    re.compile(r"validade\s*[:\-]?\s*(?:at[eé]\s*[:\-]?\s*)?(\d{2}/\d{2}/\d{4})", re.IGNORECASE),
    re.compile(r"at[eé]\s+(?:o\s+dia\s+)?(\d{2}/\d{2}/\d{4})", re.IGNORECASE),
]
_EMISSAO = re.compile(
    r"(?:emitid[ao]\s+(?:gratuitamente\s+)?(?:[àa]s?\s+[\d:]+\s+)?(?:d[oe]\s+dia\s+)?|data\s+d[ae]\s+emiss[ãa]o[:\s]+|expedi[çc][ãa]o[:\s]+)(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_NUMERO = re.compile(
    r"(?:certid[ãa]o\s+n[º°.:\s]+|n[uú]mero[:\s]+|controle[:\s]+)([A-Z0-9][A-Z0-9./-]{5,40})",
    re.IGNORECASE,
)
_CODIGO = re.compile(
    r"(?:c[oó]digo\s+de\s+(?:controle|autentica[çc][ãa]o|verifica[çc][ãa]o)[:\s]+)([A-Z0-9][A-Z0-9.-]{5,60})",
    re.IGNORECASE,
)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def texto_do_pdf(dados: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover - dependência opcional
        return ""
    try:
        leitor = PdfReader(io.BytesIO(dados))
        return "\n".join((pagina.extract_text() or "") for pagina in leitor.pages)
    except Exception:
        return ""


def _para_data(texto: str) -> date | None:
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None


def data_de_validade(texto: str) -> date | None:
    for padrao in _VALIDADES:
        if achou := padrao.search(texto):
            if data := _para_data(achou.group(1)):
                return data
    return None


def data_de_emissao(texto: str) -> date | None:
    if achou := _EMISSAO.search(texto):
        return _para_data(achou.group(1))
    datas = [d for m in _DATA.finditer(texto) if (d := _para_data(m.group(0)))]
    return min(datas) if datas else None


def numero_da_certidao(texto: str) -> str | None:
    if achou := _NUMERO.search(texto):
        return achou.group(1).strip(" .")
    return None


def codigo_de_verificacao(texto: str) -> str | None:
    if achou := _CODIGO.search(texto):
        return achou.group(1).strip(" .")
    return None


def situacao(texto: str) -> SituacaoCertidao:
    """Classifica a situação declarada no documento.

    A palavra "regularidade" sozinha não serve de prova: ela aparece no
    cabeçalho de páginas da Caixa que dizem justamente o contrário
    ("Situação de Regularidade do Empregador — não foi possível verificar").
    Só o nome do documento emitido conta.
    """
    plano = _sem_acento(texto).upper()
    if re.search(r"POSITIVA\s+COM\s+EFEITOS?\s+DE\s+NEGATIVA", plano):
        return SituacaoCertidao.POSITIVA_COM_EFEITO_NEGATIVO
    if re.search(r"CERTID[AÃ]O\s+NEGATIVA|CERTIFICADO\s+DE\s+REGULARIDADE|\bCRF\b", plano):
        return SituacaoCertidao.NEGATIVA
    if re.search(r"CERTID[AÃ]O\s+POSITIVA|CONSTAM\s+DEBITOS|EXISTEM\s+DEBITOS", plano):
        return SituacaoCertidao.POSITIVA
    if "NEGATIVA" in plano:
        return SituacaoCertidao.NEGATIVA
    if "POSITIVA" in plano:
        return SituacaoCertidao.POSITIVA
    return SituacaoCertidao.NAO_IDENTIFICADA


def analisar(dados: bytes | None, texto_pagina: str = "") -> dict:
    """Extrai tudo o que der do documento; campos ausentes voltam como None."""
    texto = (texto_do_pdf(dados) if dados else "") or texto_pagina
    return {
        "texto": texto,
        "emitida_em": data_de_emissao(texto),
        "valida_ate": data_de_validade(texto),
        "numero": numero_da_certidao(texto),
        "codigo_verificacao": codigo_de_verificacao(texto),
        "situacao": situacao(texto),
    }
