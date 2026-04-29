@echo off
REM ============================================
REM DocAI Intelligence - Script de Setup Demo
REM ============================================

echo.
echo ========================================
echo   DocAI Intelligence - Setup Demo
echo ========================================
echo.

REM Verificar Python
echo [1/7] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo ERRO: Python nao encontrado. Instale em python.org
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)
echo       Python OK

REM Verificar Node.js
echo [2/7] Verificando Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Node.js nao encontrado. Instale em nodejs.org
    pause
    exit /b 1
)
echo       Node.js OK

REM Criar ambiente virtual Python
echo [3/7] Criando ambiente virtual...
cd /d %~dp0..
if not exist "venv" (
    %PYTHON% -m venv venv
    echo       Ambiente virtual criado
) else (
    echo       Ambiente virtual ja existe
)

REM Ativar ambiente e instalar dependencias
echo [4/7] Instalando dependencias do backend...
call venv\Scripts\activate.bat
pip install -r src\requirements.txt --quiet
echo       Dependencias backend OK

REM Configurar banco de dados
echo [5/7] Configurando banco de dados...
cd src
python manage.py migrate --run-syncdb
echo       Banco de dados OK

REM Criar superusuario se nao existir
echo [6/7] Verificando superusuario...
python -c "from django.contrib.auth import get_user_model; User = get_user_model(); print('existe') if User.objects.filter(username='admin').exists() else exit(1)" 2>nul
if %errorlevel% neq 0 (
    echo       Criando usuario admin...
    python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@docai.com', 'admin123')"
    echo       Usuario: admin / Senha: admin123
) else (
    echo       Usuario admin ja existe
)
cd ..

REM Instalar dependencias frontend
echo [7/7] Instalando dependencias do frontend...
cd frontend
call npm install --silent 2>nul
cd ..
echo       Dependencias frontend OK

echo.
echo ========================================
echo   Setup concluido com sucesso!
echo ========================================
echo.
echo   Credenciais de acesso:
echo   Usuario: admin
echo   Senha:   admin123
echo.
echo   Para iniciar, execute:
echo   .\scripts\start_demo.bat
echo.
echo ========================================
pause
