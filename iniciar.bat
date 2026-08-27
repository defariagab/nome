@echo off
REM Abre o sistema de certidoes no Windows.
cd /d "%~dp0"
python iniciar.py
if errorlevel 1 pause
