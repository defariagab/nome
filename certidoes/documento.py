"""CPF/CNPJ: normalização, validação e formatação."""

from __future__ import annotations

import re

_SO_DIGITOS = re.compile(r"\D+")


def apenas_digitos(valor: str | None) -> str:
    return _SO_DIGITOS.sub("", valor or "")


def _digito(base: str, pesos: list[int]) -> str:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def cpf_valido(valor: str) -> bool:
    cpf = apenas_digitos(valor)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    d1 = _digito(cpf[:9], list(range(10, 1, -1)))
    d2 = _digito(cpf[:9] + d1, list(range(11, 1, -1)))
    return cpf[9:] == d1 + d2


def cnpj_valido(valor: str) -> bool:
    cnpj = apenas_digitos(valor)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = _digito(cnpj[:12], pesos1)
    d2 = _digito(cnpj[:12] + d1, pesos2)
    return cnpj[12:] == d1 + d2


def valido(valor: str) -> bool:
    limpo = apenas_digitos(valor)
    if len(limpo) == 11:
        return cpf_valido(limpo)
    if len(limpo) == 14:
        return cnpj_valido(limpo)
    return False


def tipo_pessoa(valor: str) -> str:
    return "PF" if len(apenas_digitos(valor)) == 11 else "PJ"


def formatar(valor: str) -> str:
    """Formata com pontuação, como os sites dos órgãos costumam exigir."""
    d = apenas_digitos(valor)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return valor or ""


def raiz_cnpj(valor: str) -> str:
    """Os 8 primeiros dígitos (matriz), usados por certidões que abrangem a raiz."""
    return apenas_digitos(valor)[:8]
