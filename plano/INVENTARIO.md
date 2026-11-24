# Inventário de pontos de contato com Airflow e Docker

Levantamento completo dos pontos de contato com Airflow e Docker em `src/` e `rodou_dashboard/app/` (cobertura 100% do comando `grep -rn --exclude-dir=__pycache__ "airflow\|api/v2\|LOGS_DIR\|docker\|subprocess" src/ rodou_dashboard/app/`), além das variáveis e conexões em uso.

---

## 1. Imports e referências `airflow.*` em `src/`

| Arquivo | Linha(s) | O que faz | Substituto previsto | Sprint |
|---|---|---|---|---|
| `src/ai/executive_summary.py` | 1 | `from airflow.sdk import Variable` (usado na L108 para `api_key_var`) | `compat/airflow_shim` (`Variable.get` lendo provedor local) | Sprint 1 |
| `src/ai/provider.py` | 2 | `from airflow.sdk import Variable` (L24-26: `AZURE_OPENAI_*`) | `compat/airflow_shim` (`Variable.get`) | Sprint 1 |
| `src/hooks/doesp_hook.py` | 22 | `from airflow.sdk.bases.hook import BaseHook` | `compat/airflow_shim` (`BaseHook`) | Sprint 1 |
| `src/hooks/dou_hook.py` | 13 | `from airflow.sdk.bases.hook import BaseHook` | `compat/airflow_shim` (`BaseHook`) | Sprint 1 |
| `src/hooks/inlabs_hook_sql_mode.py` | 18 | `from airflow.providers.postgres.hooks.postgres import PostgresHook` | `compat/airflow_shim` (`PostgresHook` sobre `psycopg`/SQLAlchemy) | Sprint 1 / 4 |
| `src/hooks/inlabs_hook.py` | 12, 14, 15 | `BaseHook`, `# PostgresHook` (comentado), `Variable` (L477: `api_key_var`) | `compat/airflow_shim` (`BaseHook`, `Variable`) | Sprint 1 |
| `src/notification/email_sender.py` | 9 | `from airflow.utils.email import send_email` | Stub no shim (`NotImplementedError`); painel já usa `email_service.py` | Sprint 1 |
| `src/notification/failure_sender.py` | 15, 17, 18, 20 | `send_email`, `BaseHook`, `Variable`, `SlackNotifier` | Stubs no shim (`NotImplementedError`); falha tratada pelo `LocalExecutor` | Sprint 1 / 2 |
| `src/utils/open_search/indexer.py` | 60 | `from airflow.providers.postgres.hooks.postgres import PostgresHook` | Fora da suíte local (`test_shim_imports.py` exclui); removido no Sprint 8 se não usado | Sprint 1 / 8 |
| `src/utils/open_search/config.py` | 2, 7 | Docstring + `from airflow.sdk import Variable` (`RO_DOU_INLABS_USE_OPENSEARCH`, `OPENSEARCH_*`) | `compat/airflow_shim` (`Variable.get` com default) | Sprint 1 |
| `src/utils/select_terms.py` | 8, 9, 12, 15, 32, 50, 58, 117 | `Variable`, `BaseHook`, `MsSqlHook` (opcional), `PostgresHook`, `select_terms_from_airflow_variable` | `compat/airflow_shim` (`Variable`, `BaseHook`, `PostgresHook`, stub `MsSqlHook`) | Sprint 1 |
| `src/parsers.py` | 10, 46, 47, 57 | `from airflow.sdk import Variable`; suporte a `from_airflow_variable` no parser YAML | `compat/airflow_shim` (`Variable`) | Sprint 1 |
| `src/schemas.py` | 66 | Campo `from_airflow_variable: Optional[str]` no schema Pydantic | Mantido para compatibilidade com upstream | Sprint 1 |
| `src/dou_dag_generator.py` | 20–31, 461, 601, 603, 615–624, 678–679 | Imports de `DAG`, `TaskGroup`, `Variable`, `Dataset`, `EmptyOperator`, `PythonOperator`, `AssetOrTimeSchedule`, `CronTriggerTimetable` e geração de DAGs | Não importado no modo local (`runner.py` chama `searchers.py` direto); arquivo removido no Sprint 8 | Sprint 2 / 8 |

---

## 2. Chamadas HTTP à API do Airflow (`/api/v2`, `/auth/token`) no painel

| Arquivo | Linha(s) | O que faz | Substituto previsto | Sprint |
|---|---|---|---|---|
| `rodou_dashboard/app/services/airflow_service.py` | 39, 57–60, 80 | `get_airflow_url()`, `get_airflow_auth()` (JWT em `POST /auth/token` com `AIRFLOW_USER`/`AIRFLOW_PASSWORD`) | Isolado em `AirflowExecutor`; removido no Sprint 8 | Sprint 2 / 8 |
| `rodou_dashboard/app/services/airflow_service.py` | 84, 101–110 | `trigger_airflow_dag`: `PATCH /api/v2/dags/{dag_id}` (unpause) + `POST /api/v2/dags/{dag_id}/dagRuns` | `Executor.trigger()` (`LocalExecutor` no modo local) | Sprint 2 |
| `rodou_dashboard/app/services/airflow_service.py` | 161, 167–170 | `toggle_airflow_dag`: `PATCH /api/v2/dags/{dag_id}` (`is_paused`) | `Executor.pause()` / `Executor.unpause()` | Sprint 2 |
| `rodou_dashboard/app/services/airflow_service.py` | 201–216 | `wait_for_specific_dag_runs`: polling em `GET /api/v2/dags/{dag_id}/dagRuns/{run_id}` | `Executor.wait(run_ids, timeout)` | Sprint 2 |
| `rodou_dashboard/app/services/airflow_service.py` | 239–245 | `wait_for_dag_discovery`: polling em `GET /api/v2/dags/{dag_id}` | Desnecessário no modo local (`temp_*` roda em memória) | Sprint 2 |
| `rodou_dashboard/app/services/airflow_service.py` | 258–267 | `get_active_dag_runs`: `GET /api/v2/dags/{did}/dagRuns?order_by=-run_after&limit=30` | `Executor.last_runs()` / `job_runs` no SQLite | Sprint 2 |
| `rodou_dashboard/app/routes/admin.py` | 132–155 | Sincroniza conexão `smtp_default` via `GET`/`PATCH`/`POST /api/v2/connections/smtp_default` | No modo local, lê direto do SQLite (`settings`) via shim/`email_service` | Sprint 2 / 3 |
| `rodou_dashboard/app/routes/admin.py` | 177–198 | Sincroniza conexão `inlabs_portal` via `GET`/`PATCH`/`POST /api/v2/connections/inlabs_portal` | No modo local, lê direto do SQLite (`settings`) via shim | Sprint 2 / 4 |
| `rodou_dashboard/app/routes/dags.py` | 13, 55, 82, 91 | `fetch_mentions_from_dag_run`: busca `taskInstances` e XCom `return_value` via `/api/v2/dags/.../xcomEntries/return_value` | `Executor.result(run_id)` lendo JSON de `job_runs` | Sprint 2 |
| `rodou_dashboard/app/routes/dags.py` | 294–295, 640–641, 673 | `toggle_airflow_dag` ao pausar/ativar rotina | `get_executor().pause/unpause()` + reload do `scheduler` | Sprint 2 / 3 |
| `rodou_dashboard/app/routes/dags.py` | 568–590 | Sincroniza `smtp_default` via `/api/v2/connections/smtp_default` no assistente | Condicional ao executor Airflow; modo local usa SQLite | Sprint 2 |
| `rodou_dashboard/app/routes/dags.py` | 721–724 | `DELETE /api/v2/dags/{dag_id}` ao excluir rotina | `scheduler.reload()` no modo local | Sprint 2 / 3 |
| `rodou_dashboard/app/routes/dags.py` | 766, 1283 | Import de `normalize_date_str` de `airflow_service` | Mover `normalize_date_str` para módulo utilitário neutro (`runtime/` ou `services/`) | Sprint 2 |
| `rodou_dashboard/app/routes/dags.py` | 830–870, 911 | Polling de status e coleta de menções via `/api/v2/dags/.../dagRuns` | `get_executor().status()` / `last_runs()` / `result()` | Sprint 2 |
| `rodou_dashboard/app/routes/dags.py` | 1004–1011, 1088, 1158–1254 | Disparo avulso e busca por data (`trigger_airflow_dag`, `wait_for_specific_dag_runs`, `wait_for_dag_discovery`, `ro-dou_inlabs_load_pg`) | `get_executor().trigger()` + `wait()`; INLABS local no Sprint 4 | Sprint 2 / 4 |
| `rodou_dashboard/app/routes/dags.py` | 1111–1114, 1933–1936 | `DELETE /api/v2/dags/{temp_dag_id}` para limpar DAGs temporárias | Eliminado no modo local (execução em memória sem arquivo YAML temporário) | Sprint 2 |
| `rodou_dashboard/app/routes/dags.py` | 1415, 1449, 1526–1575, 1631, 1712, 1816, 1849 | Busca mensal: dispara `ro-dou_inlabs_load_pg`, `pesquisa_cnpj_*` ou `temp_monthly_dou_*`, faz polling e lê XCom | `get_executor()` + `LocalExecutor` em memória + `inlabs_loader` | Sprint 2 / 4 |
| `rodou_dashboard/app/services/dag_config_service.py` | 204, 235–240, 264–266 | `cleanup_stale_temp_dags`: consulta `dagRuns` e envia `DELETE /api/v2/dags/{dag_id}` | Eliminado no modo local (sem DAGs temporárias) | Sprint 2 |

---

## 3. Logs do Airflow (`LOGS_DIR`), `docker`, `subprocess` e caminhos de container

| Arquivo | Linha(s) | O que faz | Substituto previsto | Sprint |
|---|---|---|---|---|
| `rodou_dashboard/app/routes/admin.py` | 13, 275–277 | `LOGS_DIR = os.path.join(BASE_DIR, "mnt", "airflow-logs")`; limpeza de logs antigos | Diretório `logs/` gerenciado via `platformdirs` | Sprint 3 |
| `rodou_dashboard/app/routes/dags.py` | 73, 113–117 | Fallback lendo XCom/resultado dos arquivos de log em `LOGS_DIR` (`attempt=*.log`) | `Executor.result(run_id)` direto de `job_runs` | Sprint 2 |
| `rodou_dashboard/app/routes/dags.py` | 1119, 1941 | Remove `mnt/airflow-logs/dag_id={temp_dag_id}` após busca temporária | Eliminado no modo local (`logs/runs/<run_id>.log` único) | Sprint 2 / 3 |
| `rodou_dashboard/app/services/dag_config_service.py` | 11, 112–115 | `LOGS_DIR` e `get_last_search_time()` varrendo `dag_id=pesquisa_cnpj*` | `job_runs` + APScheduler (`get_next_search_time`) | Sprint 2 / 3 |
| `rodou_dashboard/app/services/dag_config_service.py` | 50 | `touch_dag_generator()` toca `/opt/airflow/dags/ro_dou_src/dou_dag_generator.py` | `scheduler.reload()` no modo local | Sprint 3 |
| `rodou_dashboard/app/services/dag_config_service.py` | 270–272 | Remove pastas temporárias em `LOGS_DIR` | Eliminado no modo local | Sprint 2 / 3 |
| `rodou_dashboard/app/services/airflow_service.py` | 5, 142–152, 181 | `import subprocess` e fallback `docker compose exec -T airflow-scheduler airflow dags ...` | Isolado em `AirflowExecutor`; removido no Sprint 8 | Sprint 2 / 8 |
| `rodou_dashboard/app/services/sync_cnpj.py` | 24–25 | Comentário sobre mapeamento `/data` no Docker | `platformdirs` (`user_data_dir`) | Sprint 3 |
| `rodou_dashboard/app/services/inlabs_service.py` | 14–15 | Default `postgresql+pg8000://airflow:airflow@postgres:5432/inlabs` e detecção `/.dockerenv` | Configuração do PostgreSQL portátil (`127.0.0.1:54329`) | Sprint 4 |

---

## 4. Variáveis e Conexões do Airflow em uso

| Identificador | Tipo | Onde é usado | Origem no modo local | Sprint |
|---|---|---|---|---|
| `inlabs_portal` | Connection | `dag_load_inlabs/ro_dou_inlabs_load_pg_dag.py` (login no portal INLABS); sincronizado por `admin.py:182` | SQLite (`settings`: usuário e senha INLABS) via `compat/airflow_shim` | Sprint 1 / 4 |
| `inlabs_db` | Connection | `src/hooks/inlabs_hook.py:41` (`CONN_ID`), `src/hooks/inlabs_hook_sql_mode.py`, `src/utils/open_search/indexer.py:24` | PostgreSQL portátil (`127.0.0.1:<porta>`, senha gerada no SQLite) via `compat/airflow_shim` | Sprint 1 / 4 |
| `smtp_default` | Connection | `src/notification/email_sender.py`, `src/notification/failure_sender.py`; sincronizado por `admin.py:137` e `dags.py:572` | SQLite (`settings`) via `email_service.py` (e shim se necessário) | Sprint 1 / 2 |
| `path_tmp` | Variable | `dag_load_inlabs/ro_dou_inlabs_load_pg_dag.py` (diretório temporário para ZIPs/XMLs do INLABS) | Diretório temporário seguro em `%LOCALAPPDATA%\Registrale\inlabs\tmp` (Sprint 4) | Sprint 4 |
| `AZURE_OPENAI_*` | Variable | `src/ai/provider.py:24-26` | `compat/airflow_shim` (`Variable.get(..., default=None)`) | Sprint 1 |
| `email_admin` | Variable | `src/notification/failure_sender.py:77` | `compat/airflow_shim` (`Variable.get(..., default=None)`) | Sprint 1 |
| `RO_DOU_INLABS_USE_OPENSEARCH`, `OPENSEARCH_*` | Variable | `src/utils/open_search/config.py:12-35` | `compat/airflow_shim` (`Variable.get(..., default=...)`) | Sprint 1 |
