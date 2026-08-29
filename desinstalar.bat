@echo off
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"
title Registrale-DOU - Desinstalador

REM ================================================================
REM Registrale-DOU - Desinstalador Automatizado para Windows
REM ================================================================

echo.
echo ==================================================================
echo                  REGISTRALE-DOU - MONITOR DOU
echo                    Desinstalador do Sistema
echo ==================================================================
echo.
echo  ATENCAO: Este processo ira:
echo   - Parar e remover todos os containers Docker (Postgres, Airflow, Dashboard)
echo   - Apagar os volumes e bancos de dados locais (/data, /mnt/pgdata)
echo   - Limpar arquivos temporarios e sessoes
echo.

:confirm_prompt
set /p "CONFIRM=Tem certeza que deseja desinstalar e apagar tudo? [S/N]: "
if /i "%CONFIRM%"=="N" goto cancel_uninstall
if /i not "%CONFIRM%"=="S" (
    echo Opcao invalida. Digite S para Sim ou N para Nao.
    goto confirm_prompt
)

echo.
echo ---------------------------------------------------------------
echo [1/3] Parando e removendo containers e volumes Docker...
echo ---------------------------------------------------------------

docker compose down -v --remove-orphans
if errorlevel 1 (
    echo   [AVISO] Docker compose retornou erro ao parar containers.
) else (
    echo   [OK] Containers e volumes Docker removidos.
)
echo.

echo ---------------------------------------------------------------
echo [2/3] Liberando permissoes de arquivos do Windows...
echo ---------------------------------------------------------------

if exist "mnt" (
    takeown /f "mnt" /r /d y >nul 2>&1
    icacls "mnt" /grant "%username%":F /t >nul 2>&1
    echo   [OK] Permissoes da pasta mnt liberadas.
)

if exist "data" (
    takeown /f "data" /r /d y >nul 2>&1
    icacls "data" /grant "%username%":F /t >nul 2>&1
    echo   [OK] Permissoes da pasta data liberadas.
)
echo.

echo ---------------------------------------------------------------
echo [3/3] Removendo dados persistidos e arquivos gerados...
echo ---------------------------------------------------------------

if exist "mnt" (
    rd /s /q "mnt" >nul 2>&1
    echo   [OK] Pasta mnt removida.
)

if exist "data" (
    rd /s /q "data" >nul 2>&1
    echo   [OK] Pasta data removida.
)

if exist "flask_sessions" (
    rd /s /q "flask_sessions" >nul 2>&1
    echo   [OK] Pasta flask_sessions removida.
)

if exist ".env" (
    del /f /q ".env" >nul 2>&1
    echo   [OK] Arquivo .env removido.
)
echo.

echo ==================================================================
echo       Desinstalacao e limpeza concluidas com sucesso!
echo ==================================================================
echo.
echo   Todos os containers, dados do PostgreSQL, SQLite e sessoes
echo   foram removidos do seu computador.
echo.
echo   Caso deseje reinstalar futuramente, basta executar instalar.bat.
echo ==================================================================
echo.
pause
exit /b 0

:cancel_uninstall
echo.
echo Desinstalacao cancelada pelo usuario. Nenhuma alteracao foi feita.
echo.
pause
exit /b 0
