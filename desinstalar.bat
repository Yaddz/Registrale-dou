@echo off
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
title Registrale-DOU - Desinstalador
cd /d "%TEMP%"

REM ================================================================
REM Registrale-DOU - Desinstalador Automatizado para Windows
REM ================================================================

echo.
echo ==================================================================
echo                  REGISTRALE-DOU - MONITOR DOU
echo                    Desinstalador do Sistema
echo ==================================================================
echo.
echo  Selecione a opcao de desinstalacao desejada:
echo.
echo   [1] DESINSTALACAO COMPLETA (Recomendado para remocao total)
echo       - Para e remove todos os containers e redes Docker
echo       - Remove todos os volumes nomeados e imagens locais do Docker
echo       - Exclui TODOS os arquivos, dados, logs e a pasta do projeto
echo.
echo   [2] LIMPEZA DE DADOS (Reset para reinstalacao)
echo       - Para e remove containers e volumes Docker
echo       - Apaga bancos de dados locais (/data, /mnt), logs e sessoes
echo       - Mantem o codigo-fonte para permitir reinstalar via instalar.bat
echo.
echo   [3] CANCELAR
echo       - Nenhuma alteracao sera feita no sistema
echo.
echo ==================================================================
echo.

:prompt_choice
set /p "CHOICE=Digite o numero da opcao desejada [1, 2 ou 3]: "
if "%CHOICE%"=="1" goto complete_uninstall
if "%CHOICE%"=="2" goto data_cleanup
if "%CHOICE%"=="3" goto cancel_uninstall
echo Opcao invalida. Digite 1, 2 ou 3.
goto prompt_choice

:complete_uninstall
echo.
echo ==================================================================
echo  CONFIRMACAO DE DESINSTALACAO COMPLETA
echo ==================================================================
echo  ATENCAO: Esta acao ira EXCLUIR DEFINITIVAMENTE:
echo   - Todos os containers e volumes Docker do Registrale-DOU
echo   - Todos os bancos de dados locais e historico
echo   - A pasta inteira do projeto em:
echo     "%PROJECT_DIR%"
echo.
set /p "CONFIRM_ALL=Deseja realmente apagar TODOS os arquivos do projeto? [S/N]: "
if /i not "%CONFIRM_ALL%"=="S" goto cancel_uninstall

echo.
echo ---------------------------------------------------------------
echo [1/4] Parando e removendo containers, volumes e imagens Docker...
echo ---------------------------------------------------------------
cd /d "%PROJECT_DIR%" 2>nul
docker compose down -v --rmi local --remove-orphans >nul 2>&1
docker volume rm registrale-dou_postgres-data registrale-dou_smtp4dev-data >nul 2>&1
docker network rm registrale-dou_default >nul 2>&1
echo   [OK] Containers, volumes e redes Docker removidos.
echo.

echo ---------------------------------------------------------------
echo [2/4] Liberando permissoes de arquivos do Windows...
echo ---------------------------------------------------------------
cd /d "%TEMP%"
if exist "%PROJECT_DIR%" (
    takeown /f "%PROJECT_DIR%" /r /d y >nul 2>&1
    icacls "%PROJECT_DIR%" /grant "%username%":F /t >nul 2>&1
    echo   [OK] Permissoes liberadas.
)
echo.

echo ---------------------------------------------------------------
echo [3/4] Removendo todos os arquivos e diretorios do projeto...
echo ---------------------------------------------------------------
REM Criar script temporario em %TEMP% para poder remover a propria pasta do projeto
set "TEMP_SCRIPT=%TEMP%\registrale_self_remove_%RANDOM%.bat"
(
    echo @echo off
    echo timeout /t 2 /nobreak ^>nul
    echo powershell -NoProfile -Command "try { Remove-Item -LiteralPath '%PROJECT_DIR%' -Recurse -Force -ErrorAction Stop } catch { Start-Sleep -Seconds 2; Remove-Item -LiteralPath '%PROJECT_DIR%' -Recurse -Force -ErrorAction SilentlyContinue }"
    echo if not exist "%PROJECT_DIR%" (
    echo     echo.
    echo     echo ==================================================================
    echo     echo       Desinstalacao Completa Concluida com Sucesso!
    echo     echo ==================================================================
    echo     echo.
    echo     echo   Todos os containers, volumes Docker e arquivos do Registrale-DOU
    echo     echo   foram completamente excluidos do seu computador.
    echo     echo ==================================================================
    echo     echo.
    echo ) else (
    echo     echo   [AVISO] Alguns arquivos podem estar em uso por outro programa.
    echo     echo           Voce pode excluir a pasta manualmente se desejar.
    echo )
    echo pause
    echo del "%%~f0" ^>nul 2^>^&1
    echo exit
) > "%TEMP_SCRIPT%"

echo   [OK] Delegando remocao final ao assistente temporario...
start "" "%TEMP_SCRIPT%"
exit

:data_cleanup
echo.
echo ---------------------------------------------------------------
echo [1/3] Parando e removendo containers e volumes Docker...
echo ---------------------------------------------------------------
cd /d "%PROJECT_DIR%"
docker compose down -v --remove-orphans
docker volume rm registrale-dou_postgres-data registrale-dou_smtp4dev-data >nul 2>&1
if errorlevel 1 (
    echo   [AVISO] Docker compose retornou aviso ao parar containers.
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
echo [3/3] Removendo dados persistidos, logs e arquivos temporarios...
echo ---------------------------------------------------------------
if exist "mnt" rd /s /q "mnt" >nul 2>&1
if exist "data" rd /s /q "data" >nul 2>&1
if exist "flask_sessions" rd /s /q "flask_sessions" >nul 2>&1
if exist ".env" del /f /q ".env" >nul 2>&1
echo   [OK] Dados persistidos e temporarios removidos.
echo.

echo ==================================================================
echo          Limpeza de Dados Concluida com Sucesso!
echo ==================================================================
echo.
echo   Todos os containers, dados do PostgreSQL, SQLite e sessoes
echo   foram removidos. O codigo-fonte foi preservado.
echo.
echo   Para reinstalar o sistema a qualquer momento, execute instalar.bat.
echo ==================================================================
echo.
pause
exit /b 0

:cancel_uninstall
echo.
echo Desinstalacao cancelada. Nenhuma alteracao foi feita no sistema.
echo.
pause
exit /b 0
