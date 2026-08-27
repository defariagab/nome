"""Gerador mínimo de PDF, usado pelo simulador (sem dependências externas)."""

from __future__ import annotations


def _escapar(texto: str) -> str:
    limpo = texto.encode("latin-1", "replace").decode("latin-1")
    return limpo.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def gerar(linhas: list[str], titulo: str = "Documento") -> bytes:
    corpo = ["BT", "/F1 11 Tf", "14 TL", "56 760 Td", f"({_escapar(titulo)}) Tj", "T*", "T*"]
    for linha in linhas:
        corpo.append(f"({_escapar(linha)}) Tj")
        corpo.append("T*")
    corpo.append("ET")
    fluxo = "\n".join(corpo).encode("latin-1")

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(fluxo)).encode() + b" >>\nstream\n" + fluxo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    saida = bytearray(b"%PDF-1.4\n")
    posicoes = []
    for numero, objeto in enumerate(objetos, start=1):
        posicoes.append(len(saida))
        saida += f"{numero} 0 obj\n".encode() + objeto + b"\nendobj\n"

    inicio_xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n".encode()
    saida += b"0000000000 65535 f \n"
    for posicao in posicoes:
        saida += f"{posicao:010d} 00000 n \n".encode()
    saida += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n"
    ).encode()
    return bytes(saida)
