@echo off
chcp 65001 >nul
title Certidoes - demonstracao
cd /d "%~dp0"
echo Criando um escritorio ficticio para voce conhecer o sistema...
echo Os documentos gerados sao marcados como SEM VALOR LEGAL.
echo.
where py >nul 2>nul
if %errorlevel%==0 (py -3 -m certidoes demonstracao) else (python -m certidoes demonstracao)
echo.
echo Pronto. Abra o sistema com iniciar.bat.
pause
