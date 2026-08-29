@echo off
setlocal
title Registrale-DOU - Instalador

REM ================================================================
REM Registrale-DOU - Instalador Automatizado para Windows
REM ================================================================

echo.
echo ==================================================================
echo                  REGISTRALE-DOU - MONITOR DOU
echo                    Instalador Automatizado
echo ==================================================================
echo.

REM ---------------------------------------------------------------
REM ETAPA 1: Verificar Docker Desktop
REM ---------------------------------------------------------------
echo [1/4] Verificando Docker Desktop...
echo.

docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Docker Desktop nao encontrado.
    echo        Instale em: https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)
echo   [OK] Docker instalado.

docker info >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERRO] Docker Desktop nao esta em execucao.
    echo        Inicie o Docker Desktop e execute este instalador novamente.
    echo.
    pause
    exit /b 1
)
echo   [OK] Docker Desktop em execucao.
echo.

REM ---------------------------------------------------------------
REM ETAPA 2: Clonar ou Atualizar o Repositorio
REM ---------------------------------------------------------------
echo [2/4] Verificando repositorio Git...
echo.

git --version >nul 2>&1
if errorlevel 1 (
    echo   Git nao encontrado. Tentando instalar via winget...
    winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements >nul 2>&1
    set "PATH=%PATH%;C:\Program Files\Git\cmd;C:\Program Files\Git\bin"
)

if exist "docker-compose.yml" (
    echo   [OK] Repositorio detectado. Atualizando codigo...
    git pull origin main >nul 2>&1
    echo   [OK] Codigo atualizado.
) else (
    if exist "Registrale-dou\docker-compose.yml" (
        cd Registrale-dou
        echo   [OK] Pasta Registrale-dou encontrada. Atualizando...
        git pull origin main >nul 2>&1
    ) else (
        echo   Clonando repositorio Registrale-dou...
        git clone https://github.com/Yaddz/Registrale-dou.git
        if errorlevel 1 (
            echo [ERRO] Falha ao clonar o repositorio.
            pause
            exit /b 1
        )
        cd Registrale-dou
    )
)
echo.

REM ---------------------------------------------------------------
REM ETAPA 3: Executar a inicializacao com make run
REM ---------------------------------------------------------------
echo [3/4] Inicializando o ambiente...
echo.

make --version >nul 2>&1
if errorlevel 1 (
    echo   Make nao encontrado. Tentando instalar via winget...
    winget install ezwinports.make --accept-source-agreements --accept-package-agreements >nul 2>&1
    set "PATH=%PATH%;C:\Program Files (x86)\GnuWin32\bin;C:\Program Files\GnuWin32\bin"
)

make --version >nul 2>&1
if not errorlevel 1 (
    echo   Executando make run...
    make run
    goto after_setup
)

echo   Executando inicializacao direta dos containers...
if not exist ".env" copy ".env.example" ".env" >nul 2>&1
if not exist "mnt\airflow-logs" mkdir "mnt\airflow-logs" >nul 2>&1
if not exist "mnt\pgdata" mkdir "mnt\pgdata" >nul 2>&1
if not exist "data" mkdir "data" >nul 2>&1
if not exist "flask_sessions" mkdir "flask_sessions" >nul 2>&1
if not exist "dag_confs" mkdir "dag_confs" >nul 2>&1

docker compose build
docker compose up -d --remove-orphans

echo   Aguardando inicializacao do Airflow...
set ATTEMPT=0
:wait_airflow_loop
set /a ATTEMPT+=1
if %ATTEMPT% GTR 30 goto configure_airflow_direct
docker compose exec -T airflow-webserver curl -f -s -LI http://localhost:8080/ >nul 2>&1
if errorlevel 1 (
    ping 127.0.0.1 -n 4 >nul
    goto wait_airflow_loop
)

:configure_airflow_direct
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/variables' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"key\": \"termos_exemplo_variavel\", \"value\": \"LGPD\"}'" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/variables' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"key\": \"email_admin\", \"value\": \"admin@rodou.gov.br\"}'" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/variables' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"key\": \"path_tmp\", \"value\": \"/tmp\"}'" >nul 2>&1
docker compose exec -T -e PGPASSWORD=airflow postgres sh -c "psql -q -U airflow -f /sql/init-db.sql" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/connections' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"connection_id\": \"inlabs_db\", \"conn_type\": \"postgres\", \"schema\": \"inlabs\", \"host\": \"postgres\", \"login\": \"airflow\", \"password\": \"airflow\", \"port\": 5432}'" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X POST 'http://localhost:8080/api/v1/connections' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"connection_id\": \"inlabs_portal\", \"conn_type\": \"http\", \"host\": \"https://inlabs.in.gov.br/\", \"login\": \"user@email.com\", \"password\": \"password\"}'" >nul 2>&1
docker compose exec -T airflow-webserver sh -c "curl -s -X PATCH 'http://localhost:8080/api/v1/dags/ro-dou_inlabs_load_pg' -H 'Content-Type: application/json' --user 'airflow:airflow' -d '{\"is_paused\": false}'" >nul 2>&1

:after_setup
echo.

REM ---------------------------------------------------------------
REM ETAPA 4: Abrir o Dashboard no navegador
REM ---------------------------------------------------------------
echo [4/4] Abrindo o Dashboard no navegador...
start http://localhost:5000

echo.
echo ==================================================================
echo       Registrale-DOU instalado e inicializado com sucesso!
echo ==================================================================
echo.
echo   * Dashboard Web:   http://localhost:5000  (Login: admin / admin)
echo   * Apache Airflow:  http://localhost:8080  (Login: airflow / airflow)
echo   * Webmail Testes:  http://localhost:5001  (smtp4dev)
echo.
echo ------------------------------------------------------------------
echo   DICA PWA: No Chrome/Edge, clique no icone de instalacao na
echo   barra de endereco para instalar como aplicativo nativo.
echo ------------------------------------------------------------------
echo.
echo   Comandos uteis no dia a dia:
echo     docker compose up -d     (Iniciar servicos)
echo     docker compose down      (Parar servicos)
echo     docker compose logs -f   (Ver logs em tempo real)
echo.
echo ==================================================================
echo.

pause
