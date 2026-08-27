"""Padrão de nomeação dos PDFs arquivados.

O nome do arquivo é parte do produto: ele vai para a pasta do cliente, para
o e-mail e para o processo de habilitação. Precisa dizer, sozinho, de quem
é a certidão, qual é e até quando vale.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

#: modelo usado quando o escritório não define outro
PADRAO = "{sigla}_{nome}_{documento}_valida-ate-{validade}"

CAMPOS = {
    "sigla": "sigla da certidão (CNDT, CRF/FGTS...)",
    "codigo": "código interno do tipo (cndt, fgts_crf...)",
    "certidao": "nome completo da certidão",
    "orgao": "órgão emissor",
    "nome": "nome do titular",
    "documento": "CPF/CNPJ só com números",
    "documento_formatado": "CPF/CNPJ com pontuação",
    "emissao": "data de emissão (AAAA-MM-DD)",
    "validade": "último dia de validade (AAAA-MM-DD)",
    "emissao_br": "data de emissão (DD-MM-AAAA)",
    "validade_br": "validade (DD-MM-AAAA)",
    "ano": "ano da emissão",
    "numero": "número da certidão, quando o documento informa",
}

_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_ESPACOS = re.compile(r"\s+")
_REPETIDOS = re.compile(r"-{2,}")
LIMITE_NOME = 120


def limpar(valor: str) -> str:
    """Deixa o texto seguro para nome de arquivo no Windows, macOS e Linux."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", str(valor or ""))
        if unicodedata.category(c) != "Mn"
    )
    limpo = _INVALIDOS.sub("", sem_acento)
    limpo = _ESPACOS.sub("-", limpo.strip())
    limpo = _REPETIDOS.sub("-", limpo)
    return limpo.strip(" .-")


def campos(
    *,
    sigla: str, codigo: str, certidao: str, orgao: str, nome: str,
    documento: str, documento_formatado: str,
    emitida_em: date, valida_ate: date, numero: str | None = None,
) -> dict[str, str]:
    return {
        "sigla": limpar(sigla or codigo),
        "codigo": limpar(codigo),
        "certidao": limpar(certidao),
        "orgao": limpar(orgao),
        "nome": limpar(nome),
        "documento": limpar(documento),
        "documento_formatado": limpar(documento_formatado),
        "emissao": emitida_em.isoformat(),
        "validade": valida_ate.isoformat(),
        "emissao_br": emitida_em.strftime("%d-%m-%Y"),
        "validade_br": valida_ate.strftime("%d-%m-%Y"),
        "ano": str(emitida_em.year),
        "numero": limpar(numero or ""),
    }


def aplicar(padrao: str, valores: dict[str, str], extensao: str = "pdf") -> str:
    """Monta o nome do arquivo. Campo desconhecido no modelo vira vazio."""
    nome = padrao or PADRAO
    for campo in CAMPOS:
        nome = nome.replace("{" + campo + "}", valores.get(campo, ""))
    nome = re.sub(r"\{[a-z_]+\}", "", nome)          # descarta campos inexistentes
    nome = _REPETIDOS.sub("-", nome.replace("__", "_")).strip(" .-_")
    nome = (nome or "certidao")[:LIMITE_NOME]
    return f"{nome}.{extensao}"


def validar(padrao: str) -> str:
    """Devolve o padrão aceito ou explica por que não serve."""
    if not padrao.strip():
        raise ValueError("Informe um modelo de nome ou deixe o padrão do sistema.")
    usados = set(re.findall(r"\{([a-z_]+)\}", padrao))
    if desconhecidos := usados - set(CAMPOS):
        raise ValueError("Campo não existe: " + ", ".join(sorted(desconhecidos)))
    if not usados:
        raise ValueError("O modelo precisa usar ao menos um campo, como {sigla} ou {documento}.")
    if not {"documento", "documento_formatado", "nome"} & usados:
        raise ValueError("Inclua {nome} ou {documento} para identificar o titular no arquivo.")
    if not {"validade", "validade_br", "emissao", "emissao_br"} & usados:
        raise ValueError("Inclua {validade} ou {emissao} para diferenciar as versões da certidão.")
    return padrao.strip()


def exemplo(padrao: str) -> str:
    """Prévia mostrada na tela enquanto o usuário edita o modelo."""
    return aplicar(padrao, campos(
        sigla="CNDT", codigo="cndt",
        certidao="Certidão Negativa de Débitos Trabalhistas",
        orgao="Tribunal Superior do Trabalho",
        nome="Construtora Horizonte Ltda",
        documento="11222333000181", documento_formatado="11.222.333/0001-81",
        emitida_em=date(2026, 8, 27), valida_ate=date(2027, 2, 22),
        numero="12345678/2026",
    ))
