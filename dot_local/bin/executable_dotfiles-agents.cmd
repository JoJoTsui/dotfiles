@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dotfiles-agents.ps1" %*
exit /b %errorlevel%
