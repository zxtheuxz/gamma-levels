@echo off
setlocal
cd /d "%~dp0"
python -m gamma_levels.study_cli --sessions 345 --evaluation 252
pause
