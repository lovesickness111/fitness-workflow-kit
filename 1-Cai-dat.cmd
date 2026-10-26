@echo off
rem Double-click: install everything this kit needs (no API call, no publishing). Safe to run again.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\setup.ps1" -NoDoctor
if errorlevel 1 (
  echo.
  echo Cai dat CHUA xong. Chup man hinh dong loi o tren gui nguoi ho tro, hoac dong cua so nay roi bam dup lai 1-Cai-dat.cmd.
  pause
  exit /b 1
)
echo.
echo Xong. Tiep theo: bam dup 2-Nhap-key.cmd
pause
