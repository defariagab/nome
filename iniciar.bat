@echo off
chcp 65001 >nul
title Certidoes
cd /d "%~dp0"

REM O Windows pode ter o Python como "py" (lancador oficial) ou "python".
REM Tentamos o lancador primeiro: e o que evita cair na Microsoft Store.
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 iniciar.py
    goto fim
)
where python >nul 2>nul
if %errorlevel%==0 (
    python iniciar.py
    goto fim
)

echo.
echo  Nao encontrei o Python neste computador.
echo.
echo  Instale em https://www.python.org/downloads/
echo  IMPORTANTE: na primeira tela do instalador, marque
echo  "Add Python to PATH" antes de clicar em Install.
echo.
echo  Depois de instalar, feche esta janela e clique em iniciar.bat de novo.
echo.

:fim
echo.
echo  A janela pode ser fechada.
pause
