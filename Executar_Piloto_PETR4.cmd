@echo off
setlocal
cd /d "%~dp0"
python -m gamma_levels.pilot --asset PETR --ticker PETR4 --sessions 60
pause
