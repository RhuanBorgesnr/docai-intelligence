@echo off
REM ============================================
REM DocAI Intelligence - Iniciar Demo
REM ============================================

echo.
echo ========================================
echo   DocAI Intelligence - Iniciando...
echo ========================================
echo.

cd /d %~dp0..

REM Iniciar Backend em nova janela
echo Iniciando Backend (Django)...
start "DocAI Backend" cmd /k "call venv\Scripts\activate.bat && cd src && python manage.py runserver 0.0.0.0:8000"

REM Aguardar backend iniciar
timeout /t 3 /nobreak >nul

REM Iniciar Frontend em nova janela
echo Iniciando Frontend (React)...
start "DocAI Frontend" cmd /k "cd frontend && npm run dev"

REM Aguardar frontend iniciar
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   DocAI Intelligence esta rodando!
echo ========================================
echo.
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/api/docs/
echo   Admin:    http://localhost:8000/admin/
echo.
echo   Credenciais:
echo   Usuario: admin
echo   Senha:   admin123
echo.
echo   Para parar, feche as janelas do terminal
echo ========================================
echo.

REM Abrir navegador automaticamente
timeout /t 2 /nobreak >nul
start http://localhost:5173

pause
