# ==============================================================================
# Registrale-DOU & Ro-DOU Dashboard — Automation Makefile
# ==============================================================================

.PHONY: run
run: \
create-env-file \
create-logs-dir \
build \
setup-containers \
create-example-variable \
create-email-admim-variable \
create-path-tmp-variable \
create-inlabs-db \
create-inlabs-db-connection \
create-inlabs-portal-connection \
activate-inlabs-load-dag \
print-success

.PHONY: up
up:
	docker compose up -d

.PHONY: down
down:
	docker compose down

.PHONY: logs
logs:
	docker compose logs -f

.PHONY: create-azure-openai-variables
create-azure-openai-variables: \
create-azure-openai-endpoint-variable \
create-azure-openai-api-version-variable \
create-azure-openai-deployment-variable \
create-azure-openai-api-key-variable

create-env-file:
	@echo "Checking .env file..."
	@test -f .env || cp .env.example .env 2>/dev/null || cmd /c "if not exist .env copy .env.example .env" || true

create-logs-dir:
	@echo "Creating required directories..."
	@mkdir -p ./mnt/airflow-logs ./mnt/pgdata ./data ./flask_sessions ./dag_confs 2>/dev/null || cmd /c "if not exist mnt\airflow-logs mkdir mnt\airflow-logs && if not exist mnt\pgdata mkdir mnt\pgdata && if not exist data mkdir data && if not exist flask_sessions mkdir flask_sessions && if not exist dag_confs mkdir dag_confs" || true

AI_PROVIDERS ?=

build:
	@echo "Building containers (AI_PROVIDERS=$(AI_PROVIDERS))..."
	docker compose build \
		--build-arg AI_PROVIDERS="$(AI_PROVIDERS)"

setup-containers:
	@echo "Starting containers..."
	docker compose up -d --remove-orphans

create-example-variable:
	@echo "Waiting for Airflow API to start..."
	@docker compose exec -T airflow-webserver sh -c "while ! curl -f -s -LI 'http://localhost:8080/' > /dev/null; do sleep 4; done;" || docker exec airflow-webserver sh -c "while ! curl -f -s -LI 'http://localhost:8080/' > /dev/null; do sleep 4; done;"
	@echo "Creating 'termos_exemplo_variavel' Airflow variable..."
	@docker compose exec -T airflow-webserver sh -c \
		"if ! curl -f -s -LI 'http://localhost:8080/api/v1/variables/termos_exemplo_variavel' --user \"airflow:airflow\" > /dev/null; \
		then \
			curl -s -X 'POST' \
			'http://localhost:8080/api/v1/variables' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"key\": \"termos_exemplo_variavel\", \
			\"value\": \"LGPD\nlei geral de proteção de dados\nacesso à informação\" \
			}' > /dev/null; \
		fi" || true

create-email-admim-variable:
	@echo "Creating 'email_admin_variavel' in Airflow variable..."
	@docker compose exec -T airflow-webserver sh -c \
		"if ! curl -f -s -LI 'http://localhost:8080/api/v1/variables/email_admin_variavel' --user \"airflow:airflow\" > /dev/null; \
		then \
			curl -s -X 'POST' \
			'http://localhost:8080/api/v1/variables' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"key\": \"email_admin\", \
			\"value\": \"admim@rodou.gov.br\" \
			}' > /dev/null; \
		fi" || true

create-path-tmp-variable:
	@echo "Creating 'path_tmp' Airflow variable..."
	@docker compose exec -T airflow-webserver sh -c \
		"if ! curl -f -s -LI 'http://localhost:8080/api/v1/variables/path_tmp' --user \"airflow:airflow\" > /dev/null; \
		then \
			curl -s -X 'POST' \
			'http://localhost:8080/api/v1/variables' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"key\": \"path_tmp\", \
			\"value\": \"/tmp\" \
			}' > /dev/null; \
		fi" || true

create-inlabs-db:
	@echo "Creating 'inlabs' database schema..."
	@docker compose exec -T -e PGPASSWORD=airflow postgres sh -c "psql -q -U airflow -f /sql/init-db.sql > /dev/null" || docker exec -e PGPASSWORD=airflow postgres sh -c "psql -q -U airflow -f /sql/init-db.sql > /dev/null" || true

create-inlabs-db-connection:
	@echo "Creating 'inlabs_db' Airflow connection..."
	@docker compose exec -T airflow-webserver sh -c \
		"if ! curl -f -s -LI 'http://localhost:8080/api/v1/connections/inlabs_db' --user \"airflow:airflow\" > /dev/null; \
		then \
			curl -s -X 'POST' \
			'http://localhost:8080/api/v1/connections' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"connection_id\": \"inlabs_db\", \
			\"conn_type\": \"postgres\", \
			\"schema\": \"inlabs\", \
			\"host\": \"postgres\", \
			\"login\": \"airflow\", \
			\"password\": \"airflow\", \
			\"port\": 5432 \
			}' > /dev/null; \
		fi" || true

create-inlabs-portal-connection:
	@echo "Creating 'inlabs_portal' Airflow connection..."
	@docker compose exec -T airflow-webserver sh -c \
		"if ! curl -f -s -LI 'http://localhost:8080/api/v1/connections/inlabs_portal' --user \"airflow:airflow\" > /dev/null; \
		then \
			curl -s -X 'POST' \
			'http://localhost:8080/api/v1/connections' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"connection_id\": \"inlabs_portal\", \
			\"conn_type\": \"http\", \
			\"description\": \"Credencial para acesso no Portal do INLabs\", \
			\"host\": \"https://inlabs.in.gov.br/\", \
			\"login\": \"user@email.com\", \
			\"password\": \"password\" \
			}' > /dev/null; \
		fi" || true

activate-inlabs-load-dag:
	@echo "Activating 'ro-dou_inlabs_load_pg' Airflow DAG..."
	@docker compose exec -T airflow-webserver sh -c \
		"curl -s -X 'PATCH' \
			'http://localhost:8080/api/v1/dags/ro-dou_inlabs_load_pg' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"is_paused\": false \
			}' > /dev/null;" || true

print-success:
	@echo ""
	@echo "================================================================="
	@echo "🚀 Registrale-DOU & Ro-DOU Dashboard inicializados com sucesso!"
	@echo "================================================================="
	@echo "• Dashboard Web:   http://localhost:5000 (Login: admin / admin)"
	@echo "• Apache Airflow:  http://localhost:8080 (Login: airflow / airflow)"
	@echo "• Webmail Testes:  http://localhost:5001 (smtp4dev)"
	@echo "================================================================="

create-azure-openai-endpoint-variable:
	@echo "Creating 'AZURE_OPENAI_ENDPOINT' Airflow variable"
	@docker compose exec -T airflow-webserver sh -c \
		"if ! curl -f -s -LI 'http://localhost:8080/api/v1/variables/AZURE_OPENAI_ENDPOINT' --user \"airflow:airflow\" > /dev/null; \
		then \
			curl -s -X 'POST' \
			'http://localhost:8080/api/v1/variables' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"key\": \"AZURE_OPENAI_ENDPOINT\", \
			\"value\": \"https://sumarizacao-de-textos.services.ai.azure.com/\" \
			}' > /dev/null; \
		fi" || true

create-azure-openai-api-version-variable:
	@echo "Creating 'AZURE_OPENAI_API_VERSION' Airflow variable"
	@docker compose exec -T airflow-webserver sh -c \
		"if ! curl -f -s -LI 'http://localhost:8080/api/v1/variables/AZURE_OPENAI_API_VERSION' --user \"airflow:airflow\" > /dev/null; \
		then \
			curl -s -X 'POST' \
			'http://localhost:8080/api/v1/variables' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"key\": \"AZURE_OPENAI_API_VERSION\", \
			\"value\": \"2024-02-01\" \
			}' > /dev/null; \
		fi" || true

create-azure-openai-deployment-variable:
	@echo "Creating 'AZURE_OPENAI_DEPLOYMENT' Airflow variable"
	@docker compose exec -T airflow-webserver sh -c \
		"if ! curl -f -s -LI 'http://localhost:8080/api/v1/variables/AZURE_OPENAI_DEPLOYMENT' --user \"airflow:airflow\" > /dev/null; \
		then \
			curl -s -X 'POST' \
			'http://localhost:8080/api/v1/variables' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"key\": \"AZURE_OPENAI_DEPLOYMENT\", \
			\"value\": \"gpt-4o-mini\" \
			}' > /dev/null; \
		fi" || true

create-azure-openai-api-key-variable:
	@echo "Creating 'AZURE_OPENAI_API_KEY' Airflow variable"
	@docker compose exec -T airflow-webserver sh -c \
		"if ! curl -f -s -LI 'http://localhost:8080/api/v1/variables/AZURE_OPENAI_API_KEY' --user \"airflow:airflow\" > /dev/null; \
		then \
			curl -s -X 'POST' \
			'http://localhost:8080/api/v1/variables' \
			-H 'accept: application/json' \
			-H 'Content-Type: application/json' \
			--user \"airflow:airflow\" \
			-d '{ \
			\"key\": \"AZURE_OPENAI_API_KEY\", \
			\"value\": \"<your-api-key>\" \
			}' > /dev/null; \
		fi" || true

.PHONY: tests
tests:
	@echo "Executando testes no container Airflow..."
	docker compose exec -T airflow-webserver sh -c "cd /opt/airflow/tests/ && pytest -vvv --color=yes" || docker exec airflow-webserver sh -c "cd /opt/airflow/tests/ && pytest -vvv --color=yes"

.PHONY: clean
clean: down
	@echo "Limpando logs e dados persistidos..."
	-rm -rf ./mnt/airflow-logs/* ./mnt/pgdata/* ./data/database.db ./flask_sessions/* 2>/dev/null || cmd /c "if exist mnt\airflow-logs del /q mnt\airflow-logs\* && if exist mnt\pgdata del /q mnt\pgdata\* && if exist data\database.db del data\database.db && if exist flask_sessions del /q flask_sessions\*" || true

.PHONY: clean-install
clean-install: clean run
