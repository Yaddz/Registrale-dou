@echo off
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"
title Registrale-DOU - Atualizador do Sistema

REM ================================================================
REM Registrale-DOU - Atualizador Rapido para Windows
REM ================================================================

echo.
echo ==================================================================
echo                  REGISTRALE-DOU - MONITOR DOU
echo                     Atualizador do Sistema
echo ==================================================================
echo.

REM 1. Verificar Docker Desktop
echo [1/3] Verificando Docker Desktop...
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Docker Desktop nao esta em execucao.
    echo        Inicie o Docker Desktop e execute este atualizador novamente.
    echo.
    pause
    exit /b 1
)
echo   [OK] Docker Desktop em execucao.
echo.

REM 2. Puxar alteracoes do Git
echo [2/3] Atualizando codigo-fonte a partir do Git (git pull)...
echo.
git pull origin main
if errorlevel 1 (
    echo.
    echo [AVISO] Ocorreu um aviso ou falha ao executar git pull.
    echo         Verifique sua conexao ou alteracoes locais se necessario.
) else (
    echo.
    echo   [OK] Codigo-fonte atualizado com sucesso.
)
echo.

REM 3. Recompilar e reiniciar containers
echo [3/3] Recompilando imagens e reiniciando servicos...
echo.
if not exist ".env" copy ".env.example" ".env" >nul 2>&1
if not exist "mnt\airflow-logs" mkdir "mnt\airflow-logs" >nul 2>&1
if not exist "mnt\pgdata" mkdir "mnt\pgdata" >nul 2>&1
if not exist "data" mkdir "data" >nul 2>&1
if not exist "flask_sessions" mkdir "flask_sessions" >nul 2>&1
if not exist "dag_confs" mkdir "dag_confs" >nul 2>&1

docker compose up -d --build --remove-orphans
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao recompilar/iniciar os containers Docker.
    pause
    exit /b 1
)

echo.
echo   [OK] Containers atualizados e em execucao.
echo.
echo Abrindo o Dashboard no navegador...
start http://localhost:5000

echo.
echo ==================================================================
echo       Registrale-DOU atualizado e reiniciado com sucesso!
echo ==================================================================
echo.
echo   * Dashboard Web:   http://localhost:5000
echo   * Apache Airflow:  http://localhost:8080
echo.
pause
