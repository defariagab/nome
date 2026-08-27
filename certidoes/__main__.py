"""Ponto de entrada: `python -m certidoes`.

Sem argumentos abre o painel. Os demais comandos servem para manutenção e
para agendar a renovação pelo agendador do sistema operacional.
"""

from __future__ import annotations

import argparse

from .banco import iniciar as iniciar_banco


def principal(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="certidoes", description="Gestão e emissão de certidões públicas.")
    sub = parser.add_subparsers(dest="comando")
    sub.add_parser("painel", help="abre o painel no navegador (padrão)")
    sub.add_parser("renovar", help="verifica vencimentos e enfileira as renovações")
    sub.add_parser("catalogo", help="recarrega o catálogo de tipos de certidão")
    sub.add_parser("demonstracao", help="cria titulares fictícios para conhecer o sistema")
    opcoes = parser.parse_args(argumentos)

    if opcoes.comando == "renovar":
        from .agenda import varrer

        iniciar_banco()
        print(f"{len(varrer())} solicitação(ões) de renovação criada(s).")
        return 0

    if opcoes.comando == "catalogo":
        from .catalogo import carregar

        iniciar_banco()
        print(f"{carregar()} tipo(s) novo(s) no catálogo.")
        return 0

    if opcoes.comando == "demonstracao":
        from .catalogo import carregar
        from .demonstracao import povoar

        iniciar_banco()
        carregar()
        print(f"{povoar()} titular(es) de demonstração criado(s).")
        return 0

    from .servidor import executar

    executar()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
