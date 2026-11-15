@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
echo Usando: %PY%
%PY% -m pip install pandas
%PY% scripts\explorar_dados.py data\raw docs\saida-exploracao.txt
echo.
echo Pronto. Leia docs\relatorio-varredura.md e docs\saida-exploracao.txt
pause
