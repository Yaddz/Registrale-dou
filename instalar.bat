@echo off
setlocal EnableExtensions
set "PROJECT_DIR=%~dp0"
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"
cd /d "%PROJECT_DIR%"
set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;%LOCALAPPDATA%\Programs\Git\cmd;C:\Program Files\Docker\Docker\resources\bin"
title Registrale-DOU - Central de Gerenciamento e Instalacao

if not "%~1"=="" goto %~1

:main_menu
cls
echo.
echo ==================================================================
echo                  REGISTRALE-DOU - MONITOR DOU
echo          Central de Instalacao e Gerenciamento do Sistema
echo ==================================================================
echo.
echo   Selecione a opcao desejada:
echo.
echo   [1] INSTALACAO COMPLETA (Recomendado)
echo       - Verifica e instala Git, Docker Desktop e WSL (winget ou download)
echo       - Prepara diretorios e compila todos os containers Docker
echo       - Configura banco de dados e abre o Dashboard no navegador
echo.
echo   [2] ATUALIZAR SISTEMA
echo       - Puxa as ultimas melhorias do GitHub (git pull)
echo       - Recompila os containers Docker preservando seus dados
echo.
echo   [3] INSTALAR / REPARAR PRE-REQUISITOS
echo       - Instala ou atualiza Git, Docker Desktop e WSL 2
echo.
echo   [4] DESINSTALAR / LIMPAR O SISTEMA
echo       - Opcoes de limpeza de dados ou desinstalacao completa
echo.
echo   [0] SAIR
echo.
echo ==================================================================
echo.

set "MENU_CHOICE="
set /p "MENU_CHOICE=Digite o numero da opcao desejada [0 a 4]: "
if not defined MENU_CHOICE goto main_menu
set "MENU_CHOICE=%MENU_CHOICE: =%"

if "%MENU_CHOICE%"=="1" goto opt_install
if "%MENU_CHOICE%"=="2" goto opt_update
if "%MENU_CHOICE%"=="3" goto opt_prereqs
if "%MENU_CHOICE%"=="4" goto opt_uninstall
if "%MENU_CHOICE%"=="0" goto opt_exit

echo.
echo Opcao invalida. Digite um numero de 0 a 4.
pause
goto main_menu


REM ===================================================================
REM SUB-ROTINAS DE PRE-REQUISITOS (GIT, DOCKER, WSL)
REM ===================================================================

:check_and_install_git
set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;%LOCALAPPDATA%\Programs\Git\cmd"
git --version >nul 2>&1
if not errorlevel 1 (
    echo   [OK] Git instalado.
    goto :eof
)
echo   [AVISO] Git nao foi encontrado no sistema.
echo.
set /p "INSTALL_GIT=Deseja instalar o Git automaticamente agora? [S/N]: "
if /i not "%INSTALL_GIT%"=="S" (
    echo [ERRO] O Git e necessario para clonar e atualizar o projeto.
    set "PREREQ_ERROR=1"
    goto :eof
)

where winget >nul 2>&1
if not errorlevel 1 (
    echo   Instalando Git via winget...
    winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
    set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;%LOCALAPPDATA%\Programs\Git\cmd"
    git --version >nul 2>&1
    if not errorlevel 1 (
        echo   [OK] Git instalado com sucesso via winget!
        goto :eof
    )
    echo   [AVISO] Instalacao via winget nao concluiu. Tentando download direto...
) else (
    echo   [AVISO] winget nao detectado neste ambiente.
    echo   Baixando instalador oficial do Git diretamente do GitHub...
)

echo   Baixando e instalando Git em segundo plano (aguarde)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { $r = Invoke-RestMethod -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest' -Headers @{'User-Agent'='Registrale'} -TimeoutSec 10; $u = ($r.assets | Where-Object { $_.name -match '^Git-.*-64-bit\.exe$' } | Select-Object -First 1).browser_download_url } catch {}; if (-not $u) { $u = 'https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.5/Git-2.55.0.5-64-bit.exe' }; $d = Join-Path $env:TEMP 'Git-Installer.exe'; Write-Host ('  Baixando: ' + $u); if (Get-Command curl.exe -ErrorAction SilentlyContinue) { curl.exe -L --progress-bar -o $d $u } else { Invoke-WebRequest -Uri $u -OutFile $d }; Write-Host '  Instalando Git silenciosamente...'; Start-Process -FilePath $d -ArgumentList '/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS' -Wait; Remove-Item -Path $d -Force -ErrorAction SilentlyContinue"

set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin;%LOCALAPPDATA%\Programs\Git\cmd"
git --version >nul 2>&1
if not errorlevel 1 (
    echo   [OK] Git instalado com sucesso!
    goto :eof
)

echo.
echo [ERRO] Nao foi possivel concluir a instalacao automatica do Git.
echo        Por favor, baixe e instale manualmente em: https://git-scm.com/download/win
set "PREREQ_ERROR=1"
goto :eof


:check_and_install_docker
set "PATH=%PATH%;C:\Program Files\Docker\Docker\resources\bin"
docker --version >nul 2>&1
if not errorlevel 1 (
    echo   [OK] Docker instalado.
    goto :eof
)
echo   [AVISO] Docker Desktop nao foi encontrado neste computador.
echo.
set /p "INSTALL_DK=Deseja instalar o Docker Desktop agora? [S/N]: "
if /i not "%INSTALL_DK%"=="S" (
    echo [ERRO] O Docker Desktop e necessario para executar a aplicacao.
    set "PREREQ_ERROR=1"
    goto :eof
)

where winget >nul 2>&1
if not errorlevel 1 (
    echo   Instalando Docker Desktop via winget...
    winget install --id Docker.DockerDesktop -e --source winget --accept-source-agreements --accept-package-agreements
    set "PATH=%PATH%;C:\Program Files\Docker\Docker\resources\bin"
    docker --version >nul 2>&1
    if not errorlevel 1 (
        echo.
        echo   [OK] Instalador do Docker Desktop concluido via winget!
        echo   AVISO: O Windows pode solicitar reiniciar o computador para ativar
        echo   a virtualizacao do WSL. Apos reiniciar, abra o Docker Desktop
        echo   uma vez e rode este instalador novamente.
        echo.
        pause
        goto :eof
    )
    echo   [AVISO] Instalacao via winget nao concluiu. Tentando download direto...
) else (
    echo   [AVISO] winget nao detectado neste ambiente.
    echo   Baixando instalador oficial do Docker Desktop...
)

echo   Baixando Docker Desktop Installer (aprox. 600MB, aguarde)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; $u = 'https://desktop.docker.com/win/main/amd64/Docker%%20Desktop%%20Installer.exe'; $d = Join-Path $env:TEMP 'DockerDesktopInstaller.exe'; Write-Host ('  Baixando: ' + $u); if (Get-Command curl.exe -ErrorAction SilentlyContinue) { curl.exe -L --progress-bar -o $d $u } else { Invoke-WebRequest -Uri $u -OutFile $d }; Write-Host '  Executando instalador do Docker Desktop...'; Start-Process -FilePath $d -ArgumentList 'install --quiet' -Wait; Remove-Item -Path $d -Force -ErrorAction SilentlyContinue"

set "PATH=%PATH%;C:\Program Files\Docker\Docker\resources\bin"
docker --version >nul 2>&1
if not errorlevel 1 (
    echo.
    echo   [OK] Docker Desktop instalado com sucesso!
    echo   AVISO: O Windows pode solicitar reiniciar o computador para ativar
    echo   a virtualizacao do WSL. Apos reiniciar, abra o Docker Desktop
    echo   uma vez e rode este instalador novamente.
    echo.
    pause
    goto :eof
)

if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    echo.
    echo   [OK] Arquivos do Docker Desktop instalados com sucesso!
    echo   Abra o Docker Desktop pelo menu Iniciar e reinicie o instalador.
    pause
    goto :eof
)

echo.
echo [ERRO] Nao foi possivel concluir a instalacao automatica do Docker Desktop.
echo        Baixe e instale manualmente em: https://www.docker.com/products/docker-desktop/
set "PREREQ_ERROR=1"
goto :eof


:check_and_install_wsl
echo   Verificando suporte ao WSL (Windows Subsystem for Linux)...
wsl --status >nul 2>&1
if not errorlevel 1 (
    echo   [OK] WSL habilitado.
    goto :eof
)
echo   [AVISO] WSL 2 pode nao estar ativado.
set /p "CONFIRM_WSL=Deseja ativar/atualizar o WSL agora? [S/N]: "
if /i "%CONFIRM_WSL%"=="S" (
    wsl --install --no-distribution >nul 2>&1 || wsl --update >nul 2>&1
    echo   [OK] Comando WSL executado.
)
goto :eof


:ensure_docker_running
set "PATH=%PATH%;C:\Program Files\Docker\Docker\resources\bin"
docker info >nul 2>&1
if not errorlevel 1 (
    echo   [OK] Docker Desktop em execucao.
    goto :eof
)
echo   Docker Desktop nao parece estar ativo. Tentando iniciar automaticamente...
if exist "C:\Program Files\Docker\Docker\Docker Desktop.exe" (
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
)
echo   Aguardando o servico do Docker responder (ate 45 segundos)...
set DOCKER_WAIT=0
:wait_docker_loop
set /a DOCKER_WAIT+=1
if %DOCKER_WAIT% GTR 15 (
    echo.
    echo [ERRO] Docker Desktop nao esta respondendo.
    echo        Abra o Docker Desktop pelo menu Iniciar e execute este script novamente.
    echo        (Nota: Em ambientes de maquina virtual ou Windows Sandbox, certifique-se
    echo        de que a Virtualizacao Aninhada / Hyper-V esteja ativada no host).
    set "PREREQ_ERROR=1"
    goto :eof
)
docker info >nul 2>&1
if errorlevel 1 (
    ping 127.0.0.1 -n 4 >nul
    goto wait_docker_loop
)
echo   [OK] Docker Desktop conectado e em execucao!
goto :eof


REM ===================================================================
REM OPCAO 3: INSTALAR / REPARAR PRE-REQUISITOS
REM ===================================================================
:opt_prereqs
cls
echo.
echo ==================================================================
echo         Instalacao e Verificacao de Pre-Requisitos
echo ==================================================================
echo.
set "PREREQ_ERROR="
call :check_and_install_git
call :check_and_install_docker
call :check_and_install_wsl
echo.
if defined PREREQ_ERROR (
    echo [AVISO] Um ou mais pre-requisitos nao foram concluidos com sucesso.
) else (
    echo [OK] Todos os pre-requisitos foram verificados!
)
echo.
echo Pressione qualquer tecla para retornar ao menu principal...
pause >nul
goto main_menu


REM ===================================================================
REM OPCAO 1: INSTALACAO COMPLETA DO SISTEMA
REM ===================================================================
:opt_install
cls
echo.
echo ==================================================================
echo             Instalacao Completa do Registrale-DOU
echo ==================================================================
echo.

REM 1. Pre-requisitos
echo [Etapa 1/4] Verificando pre-requisitos de sistema...
echo.
set "PREREQ_ERROR="
call :check_and_install_git
if defined PREREQ_ERROR goto install_abort

call :check_and_install_docker
if defined PREREQ_ERROR goto install_abort

call :ensure_docker_running
if defined PREREQ_ERROR goto install_abort

REM 2. Repositorio Git
echo.
echo [Etapa 2/4] Verificando integridade do repositorio...
echo.
if exist "docker-compose.yml" (
    echo   [OK] Repositorio detectado na pasta atual.
    echo   Atualizando com a versao mais recente do GitHub...
    git pull origin main 2>nul
) else (
    if exist "Registrale-dou\docker-compose.yml" (
        cd Registrale-dou
        set "PROJECT_DIR=%CD%"
        echo   [OK] Pasta Registrale-dou detectada.
        git pull origin main 2>nul
    ) else (
        echo   Clonando repositorio Registrale-dou...
        git clone https://github.com/Yaddz/Registrale-dou.git
        if errorlevel 1 (
            echo.
            echo [ERRO] Falha ao clonar o repositorio do GitHub.
            echo        Verifique sua conexao com a internet.
            pause
            goto main_menu
        )
        cd Registrale-dou
        set "PROJECT_DIR=%CD%"
    )
)
echo   [OK] Codigo-fonte pronto.
echo.

REM 3. Diretorios e Containers Docker
echo [Etapa 3/4] Preparando diretorios e compilando containers Docker...
echo.
if not exist ".env" copy ".env.example" ".env" >nul 2>&1
if not exist "mnt\airflow-logs" mkdir "mnt\airflow-logs" >nul 2>&1
if not exist "mnt\pgdata" mkdir "mnt\pgdata" >nul 2>&1
if not exist "data" mkdir "data" >nul 2>&1
if not exist "flask_sessions" mkdir "flask_sessions" >nul 2>&1
if not exist "dag_confs" mkdir "dag_confs" >nul 2>&1

echo   Compilando imagens e inicializando containers (isso pode levar alguns minutos)...
echo.
docker compose up -d --build --remove-orphans
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao compilar ou iniciar os containers Docker.
    echo        Verifique se o Docker Desktop esta totalmente aberto e com memoria suficiente.
    pause
    goto main_menu
)
echo.
echo   [OK] Containers Docker ativos.
echo.

REM 4. Aguardar Airflow e Configurar Conexoes
echo [Etapa 4/4] Inicializando configuracoes do Airflow e banco de dados...
echo.
echo   Aguardando servicos web do Airflow responderem...
set ATTEMPT=0
:wait_airflow_loop
set /a ATTEMPT+=1
if %ATTEMPT% GTR 35 goto configure_airflow_direct
docker compose exec -T airflow-webserver curl -f -s -LI http://localhost:8080/ >nul 2>&1
if errorlevel 1 (
    ping 127.0.0.1 -n 4 >nul
    goto wait_airflow_loop
)

:configure_airflow_direct
echo   Configurando variaveis e conexoes do sistema...
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/variables' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"key\": \"termos_exemplo_variavel\", \"value\": \"LGPD\"}'" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/variables' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"key\": \"email_admin\", \"value\": \"admin@rodou.gov.br\"}'" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/variables' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"key\": \"path_tmp\", \"value\": \"/tmp\"}'" >nul 2>&1
docker compose exec -T -e PGPASSWORD=airflow postgres sh -c "psql -q -U airflow -f /sql/init-db.sql" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/connections' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"connection_id\": \"inlabs_db\", \"conn_type\": \"postgres\", \"schema\": \"inlabs\", \"host\": \"postgres\", \"login\": \"airflow\", \"password\": \"airflow\", \"port\": 5432}'" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/connections' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"connection_id\": \"inlabs_portal\", \"conn_type\": \"http\", \"host\": \"https://inlabs.in.gov.br/\", \"login\": \"user@email.com\", \"password\": \"password\"}'" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X PATCH 'http://localhost:8080/api/v1/dags/ro-dou_inlabs_load_pg' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"is_paused\": false}'" >nul 2>&1

echo.
echo ==================================================================
echo       Registrale-DOU instalado e configurado com sucesso!
echo ==================================================================
echo.
echo   * Dashboard Web:   http://localhost:5000  (Login: admin / admin)
echo   * Apache Airflow:  http://localhost:8080  (Login: airflow / airflow)
echo   * Webmail Testes:  http://localhost:5001  (smtp4dev)
echo.
echo   Abrindo o Dashboard no seu navegador...
start http://localhost:5000
echo.
echo Pressione qualquer tecla para retornar ao menu principal...
pause >nul
goto main_menu

:install_abort
echo.
echo [AVISO] Instalacao nao pode ser concluida. Verifique os avisos acima.
pause
goto main_menu


REM ===================================================================
REM OPCAO 2: ATUALIZAR SISTEMA
REM ===================================================================
:opt_update
cls
echo.
echo ==================================================================
echo                   Atualizacao do Sistema
echo ==================================================================
echo.

if not exist "docker-compose.yml" (
    if exist "Registrale-dou\docker-compose.yml" (
        cd Registrale-dou
        set "PROJECT_DIR=%CD%"
    ) else (
        echo.
        echo [ERRO] Arquivo docker-compose.yml nao encontrado nesta pasta.
        echo        Execute primeiro a opcao [1] para realizar a Instalacao Completa.
        pause
        goto main_menu
    )
)

set "PREREQ_ERROR="
call :ensure_docker_running
if defined PREREQ_ERROR (
    pause
    goto main_menu
)

echo [1/2] Baixando as ultimas alteracoes do GitHub (git pull)...
echo.
git pull origin main
if errorlevel 1 (
    echo.
    echo [AVISO] Ocorreu uma advertencia no git pull. Continuando com a recompilacao...
) else (
    echo.
    echo   [OK] Codigo-fonte atualizado com sucesso.
)
echo.

echo [2/2] Recompilando imagens e reiniciando servicos...
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
    echo [ERRO] Falha ao recompilar os containers.
    pause
    goto main_menu
)

echo.
echo ==================================================================
echo            Sistema Atualizado com Sucesso!
echo ==================================================================
echo.
echo   Dashboard pronto em: http://localhost:5000
start http://localhost:5000
echo.
echo Pressione qualquer tecla para retornar ao menu principal...
pause >nul
goto main_menu


REM ===================================================================
REM OPCAO 4: DESINSTALAR / LIMPAR O SISTEMA
REM ===================================================================
:opt_uninstall
cls
echo.
echo ==================================================================
echo              Central de Desinstalacao e Limpeza
echo ==================================================================
echo.
echo   Escolha a modalidade de desinstalacao:
echo.
echo   [1] DESINSTALACAO COMPLETA (Excluir Tudo)
echo       - Para todos os containers e apaga imagens/volumes Docker
echo       - Destrava permissoes do Windows (takeown/icacls)
echo       - Remove completamente todos os arquivos e pastas do projeto
echo.
echo   [2] LIMPEZA DE DADOS (Reset para Reinstalacao)
echo       - Para os containers e exclui apenas bancos de dados e volumes
echo       - Mantem os arquivos de codigo-fonte preservados
echo.
echo   [3] CANCELAR E VOLTAR
echo.
echo ==================================================================
echo.

set "UNINST_CHOICE="
set /p "UNINST_CHOICE=Digite sua opcao [1, 2 ou 3]: "

if "%UNINST_CHOICE%"=="1" goto uninst_full
if "%UNINST_CHOICE%"=="2" goto uninst_data
if "%UNINST_CHOICE%"=="3" goto main_menu
echo Opcao invalida.
pause
goto opt_uninstall

:uninst_data
echo.
echo ==================================================================
echo  CONFIRMACAO: LIMPEZA DE BANCOS E VOLUMES DOCKER
echo ==================================================================
echo  Esta acao vai parar os servicos e apagar:
echo   - Volumes Docker (postgres-data, smtp4dev-data)
echo   - Pastas locais de dados: data/, mnt/, flask_sessions/
echo.
set /p "CONFIRM_DATA=Deseja prosseguir com a limpeza dos dados? [S/N]: "
if /i not "%CONFIRM_DATA%"=="S" goto opt_uninstall

if not exist "docker-compose.yml" (
    if exist "Registrale-dou\docker-compose.yml" (
        cd Registrale-dou
        set "PROJECT_DIR=%CD%"
    )
)

echo.
echo Parando containers e removendo volumes...
docker compose down -v --remove-orphans >nul 2>&1
docker volume rm registrale-dou_postgres-data registrale-dou_smtp4dev-data >nul 2>&1

echo Apagando bancos locais e sessoes temporarias...
if exist "data" rmdir /s /q "data" 2>nul
if exist "flask_sessions" rmdir /s /q "flask_sessions" 2>nul
if exist "mnt\airflow-logs" rmdir /s /q "mnt\airflow-logs" 2>nul
if exist "mnt\pgdata" rmdir /s /q "mnt\pgdata" 2>nul

mkdir "data" 2>nul
mkdir "flask_sessions" 2>nul
mkdir "mnt\airflow-logs" 2>nul
mkdir "mnt\pgdata" 2>nul

echo.
echo   [OK] Limpeza concluida com sucesso! O ambiente esta pronto para nova instalacao.
echo.
pause
goto main_menu

:uninst_full
echo.
echo ==================================================================
echo  ATENCAO: CONFIRMACAO DE DESINSTALACAO TOTAL
echo ==================================================================
echo  Esta acao ira EXCLUIR DEFINITIVAMENTE:
echo   - Todos os containers, redes e volumes Docker
echo   - Todos os dados, empresas, rotinas e historico
echo   - O diretorio completo do projeto em:
echo     "%PROJECT_DIR%"
echo.
set /p "CONFIRM_FULL=Tem certeza absoluta que deseja excluir tudo do sistema? [S/N]: "
if /i not "%CONFIRM_FULL%"=="S" goto opt_uninstall

if not exist "docker-compose.yml" (
    if exist "Registrale-dou\docker-compose.yml" (
        cd Registrale-dou
        set "PROJECT_DIR=%CD%"
    )
)

echo.
echo [1/3] Parando e removendo recursos Docker...
docker compose down -v --rmi local --remove-orphans >nul 2>&1
docker volume rm registrale-dou_postgres-data registrale-dou_smtp4dev-data >nul 2>&1
docker network rm registrale-dou_default >nul 2>&1
echo   [OK] Recursos Docker removidos.

echo.
echo [2/3] Liberando permissoes de arquivos do Windows...
cd /d "%TEMP%"
takeown /f "%PROJECT_DIR%" /r /d y >nul 2>&1
icacls "%PROJECT_DIR%" /grant "%username%":F /t >nul 2>&1
echo   [OK] Permissoes liberadas.

echo.
echo [3/3] Finalizando a exclusao do diretorio...
set "TEMP_SCRIPT=%TEMP%\registrale_clean_exit.bat"

> "%TEMP_SCRIPT%" echo @echo off
>> "%TEMP_SCRIPT%" echo title Registrale-DOU - Concluindo Desinstalacao
>> "%TEMP_SCRIPT%" echo echo.
>> "%TEMP_SCRIPT%" echo echo Finalizando a exclusao dos arquivos...
>> "%TEMP_SCRIPT%" echo ping 127.0.0.1 -n 3 ^>nul
>> "%TEMP_SCRIPT%" echo powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2; try { Remove-Item -LiteralPath '%PROJECT_DIR%' -Recurse -Force -ErrorAction Stop } catch { Start-Sleep -Seconds 2; Remove-Item -LiteralPath '%PROJECT_DIR%' -Recurse -Force -ErrorAction SilentlyContinue }"
>> "%TEMP_SCRIPT%" echo echo.
>> "%TEMP_SCRIPT%" echo echo ==================================================================
>> "%TEMP_SCRIPT%" echo echo         Desinstalacao Total Concluida com Sucesso!
>> "%TEMP_SCRIPT%" echo echo ==================================================================
>> "%TEMP_SCRIPT%" echo echo.
>> "%TEMP_SCRIPT%" echo echo Todos os arquivos e servicos foram removidos do seu computador.
>> "%TEMP_SCRIPT%" echo echo.
>> "%TEMP_SCRIPT%" echo pause
>> "%TEMP_SCRIPT%" echo del "%TEMP_SCRIPT%"

start "" "%TEMP_SCRIPT%"
exit /b 0

:opt_exit
echo.
echo Encerrando central de gerenciamento...
ping 127.0.0.1 -n 2 >nul 2>&1
exit /b 0
