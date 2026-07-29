@echo off
setlocal
pwsh.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update_open_excel_results.ps1" -WorkbookPath "%~dp0profit_rtd.xlsx"
if errorlevel 1 (
  echo.
  echo Nao foi possivel atualizar os resultados. Veja a mensagem acima.
  pause
)
endlocal
