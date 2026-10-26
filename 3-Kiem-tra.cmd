@echo off
rem Double-click: check this computer is ready (local checks only, no API call).
if not exist "%~dp0.venv\Scripts\python.exe" (echo Chua cai dat: bam dup 1-Cai-dat.cmd truoc & pause & exit /b 1)
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\manage.py" doctor
echo.
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\fitness_video.py" doctor
echo.
echo Dong ACTION = viec can lam them; OK = san sang.
echo Dong ACTION ghi "needed only for ..." thi bo qua neu ban chua dung tinh nang do.
pause
