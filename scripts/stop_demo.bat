@echo off
REM ============================================
REM DocAI Intelligence - Parar Demo
REM ============================================

echo Parando DocAI Intelligence...

REM Matar processos do Python (Django)
taskkill /F /IM python.exe /T 2>nul

REM Matar processos do Node (Vite)
taskkill /F /IM node.exe /T 2>nul

echo.
echo DocAI Intelligence parado.
echo.
pause
