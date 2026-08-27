#!/bin/bash
# Abre o sistema de certidões no macOS/Linux.
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 iniciar.py
else
  echo
  echo "  Não encontrei o Python neste computador."
  echo "  Instale em https://www.python.org/downloads/ e tente de novo."
  echo
  read -r -p "Pressione Enter para fechar."
fi
