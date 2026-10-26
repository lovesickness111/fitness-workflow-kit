@echo off
rem Double-click: log Codex CLI in with YOUR ChatGPT account (opens a browser). Used to draw fitness images.
where codex >nul 2>nul || (echo Chua co Codex CLI: bam dup 1-Cai-dat.cmd truoc. Anh se dung Gemini du phong. & pause & exit /b 1)
codex login
codex login status
echo.
pause
