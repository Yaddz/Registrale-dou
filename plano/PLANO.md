# Plano de migração: Registrale-DOU para aplicativo Windows

Fonte da verdade da migração. Cada sprint tem objetivo, escopo, tarefas, entregáveis, critério de aceite e uma seção **Registro**, que o agente executor preenche ao terminar. Regras de trabalho em [`../AGENTS.md`](../AGENTS.md); prompts prontos em [`prompts/`](prompts/).

## Decisões de arquitetura

| Tema | Decisão | Motivo |
|---|---|---|
| Execução | Executor local dentro do painel, sem Airflow | Um analista só; Airflow + Docker usam ~2 GB de RAM e exigem WSL/Docker Desktop (licença paga em empresas grandes) |
| Núcleo de busca | `src/` do upstream intacto, rodando sobre `compat/airflow_shim/` | Continuar recebendo atualizações do Ro-DOU oficial com conflitos mínimos |
| Agendamento | APScheduler num único processo | Substitui o scheduler do Airflow e corrige o agendador do Sheets duplicado pelos 2 workers do gunicorn |
| Servidor web | waitress (1 processo, várias threads) | gunicorn não roda no Windows |
| Dados do painel | SQLite (`database.db`), como hoje | Já é o banco do painel |
| Dados INLABS | PostgreSQL **portátil** gerido pelo app (binários embutidos, porta local, sem serviço do Windows) | Mantém o modo SQL do upstream (`~*`, `unaccent`) sem tradução; atualizações do upstream continuam valendo |
| Empacotamento | Python 3.11 *embeddable* + dependências + Inno Setup → `Registrale-Setup-x.y.z.exe` | Menos falso positivo de antivírus que PyInstaller e fácil de inspecionar e corrigir |
| Execução no Windows | Launcher na bandeja do sistema (pystray), início automático com o Windows, abre `http://localhost:5000`; a partir do Sprint 9, numa janela própria (pywebview/WebView2), com o navegador como reserva. Electron descartado | O analista não precisa abrir terminal; WebView2 já vem no Windows e não pesa como o Electron |
| Diretórios | Programa em `%LOCALAPPDATA%\Programs\Registrale`; dados em `%LOCALAPPDATA%\Registrale`; PDFs em `Documentos\Registrale\DOU` (configurável) | Atualizar ou reinstalar não apaga dados |
| Transição | `REGISTRALE_EXECUTOR=airflow\|local`; o modo Docker segue funcionando até o Sprint 8 | Permite comparar os dois modos lado a lado |
| Atualização do app | Verificação de nova versão nas Releases do GitHub + instalador com hash SHA-256 | Simples e auditável |
| Upstream | Merge periódico de `upstream/main` com script que reaplica as remoções e roda os testes | Requisito do projeto |

## Baseline de paridade

Gerada no Sprint 0 e usada nos Sprints 2 e 7:

- Rotina `Pesquisa_cnpj.yaml` (122 CNPJs, Seções 1/2/3 + Extras), novembro/2026 (03–23/11, 14 dias úteis; 20/11 é feriado), via API do DOU → **26 menções, 16 empresas**.
- Execuções de dia único: 19/11/2026 → 0 menções das 122 empresas; 03/11 e 23/11 → incluem SURGITEC só pela raiz (`24.684.423`).

## Visão geral

| Sprint | Entrega | Depende de |
|---|---|---|
| 0 | Base congelada, baseline gravada, ambiente de desenvolvimento local | — |
| 1 | Núcleo `src/` rodando sem Airflow (shim) + procedimento de upstream | 0 |
| 2 | Executor local da busca DOU + camada de executor no painel | 1 |
| 3 | Agendador, servidor waitress, ciclo de vida e logs | 2 |
| 4 | INLABS local (PostgreSQL portátil + carga) | 2 (pode correr em paralelo ao 3) |
| 5 | Arquivo automático do PDF integral do DOU | 3 |
| 6 | Instalador Windows, launcher, migração de dados e atualização | 3, 4, 5 |
| 6.1 | Contingência INLABS: busca pelo PDF integral (feito) + pendências | 6 |
| 7 | Validação de paridade 100% e homologação com o analista | 6.1 |
| 8 | Remoção de Docker/Airflow, limpeza do git, novo README | Aprovação escrita do Sprint 7 |
| 9 | Pasta e organização dos PDFs no onboarding, janela própria (pywebview) e ícone do site no `.exe` | 8 |
| Backlog | Exportar a página com a menção destacada (standby) | 5 |

---

## Sprint 0: Base e baseline

**Objetivo:** congelar o estado atual que funciona e gravar a referência contra a qual o modo local será comparado.

**Tarefas**
1. Com autorização do usuário, commitar o trabalho pendente em `main` (correções pós-merge, regra de CNPJ por raiz, seções, `AGENTS.md`, `plano/`), em commits separados por assunto.
2. Criar a tag `baseline-docker` e a branch `feature/modo-local`.
3. Gravar fixtures de paridade a partir do modo Docker:
   - `tests/fixtures/baseline/nov2026_mentions.json`: menções de novembro (empresa, CNPJ, data, seção, link e `matched_cnpj`).
   - `tests/fixtures/baseline/dou_api/*.json`: respostas brutas da API do DOU para uns 6 casos (CNPJ completo, filial, raiz isolada, trecho truncado, sem resultado, paginação), para testes offline.
   - `tests/fixtures/baseline/run_result_*.json`: o `return_value` (XCom) de 2 execuções reais de `exec_search`, para fixar o contrato de resultado.
4. Documentar em `plano/INVENTARIO.md` todos os pontos de contato com o Airflow e o Docker:
   - os imports `airflow.*` em `src/`;
   - as chamadas HTTP em `rodou_dashboard/app/services/airflow_service.py`, `routes/dags.py`, `routes/admin.py` e `services/dag_config_service.py`;
   - a leitura de logs do Airflow (`LOGS_DIR`), o uso de `docker compose` e `subprocess`, e as variáveis e conexões do Airflow em uso (`inlabs_portal`, `inlabs_db`, `path_tmp`, `smtp_default`).
5. Preparar o ambiente de desenvolvimento local: `pyproject.toml` na raiz com `uv`, Python 3.11 e grupos de dependências (`core`, `dashboard`, `dev`), sem instalar Airflow.

**Entregáveis:** tag e branch, fixtures, `plano/INVENTARIO.md`, `pyproject.toml`.

**Critério de aceite**
- `git status` limpo em `feature/modo-local`.
- As fixtures reproduzem 26 menções e 16 empresas.
- O inventário cobre 100% das ocorrências encontradas por `grep -rn "airflow\|api/v2\|LOGS_DIR\|docker\|subprocess"` em `src/` e `rodou_dashboard/app/`.

**Fora de escopo:** qualquer mudança de comportamento.

**Registro:**
- **O que foi feito:**
  - Commitado trabalho pendente em `main` em 3 commits separados (`229adb8` correções pós-merge/Docker/Sheets, `e1d6ca0` regra de CNPJ por raiz e seções, `5415bfc` `AGENTS.md` e `plano/`), criada a tag `baseline-docker` em `5415bfc` e criada a branch `feature/modo-local`.
  - Gravadas as fixtures de paridade em `tests/fixtures/baseline/`:
    - `nov2026_mentions.json` (26 menções, 16 empresas, filtradas pelos 122 CNPJs de `dag_confs/Pesquisa_cnpj.yaml` a partir do SQLite do painel).
    - `dou_api/`: 6 respostas brutas da API do DOU (`cnpj_completo.json`, `filial.json`, `raiz_isolada.json`, `trecho_truncado.json`, `sem_resultado.json`, `paginacao.json`).
    - `run_result_2026-11-23.json` (4 itens) e `run_result_2026-11-19.json` (0 itens), executando `DOUSearcher.exec_search` no container `airflow-scheduler`.
  - Criado `plano/INVENTARIO.md` cobrindo 100% dos 20 arquivos (168 ocorrências) de `src/` e `rodou_dashboard/app/` encontrados pelo `grep`, além das variáveis e conexões do Airflow.
  - Criado `pyproject.toml` na raiz (Python `>=3.11,<3.12`, grupos `core`, `dashboard` e `dev`, sem Airflow).
- **Decisões tomadas:**
  - `nov2026_mentions.json` foi filtrado pelos 122 CNPJs de `Pesquisa_cnpj.yaml` porque o SQLite local continha 3 menções extras de `26461699013754` (fora da rotina principal).
  - `run_result_*.json` foi gerado executando `DOUSearcher.exec_search` diretamente no `airflow-scheduler` porque a tabela `xcom` do Postgres estava vazia.
  - `pyproject.toml` usa `[dependency-groups]` (padrão `uv`) e mantém `SQLAlchemy<2.0.0` / `Flask<2.3.0` compatíveis com o painel atual.
- **Arquivos criados/alterados:** `plano/INVENTARIO.md`, `pyproject.toml`, `tests/fixtures/baseline/nov2026_mentions.json`, `tests/fixtures/baseline/run_result_2026-11-19.json`, `tests/fixtures/baseline/run_result_2026-11-23.json`, `tests/fixtures/baseline/dou_api/*.json`, `plano/PLANO.md`.
- **Validações:**
  - `docker exec -w /opt/airflow airflow-scheduler python -m pytest -q tests -m "not live" --ignore=tests/test_e2e_dag_execution.py` → `456 passed` (0 falhas).
  - `docker exec -w /app rodou-dashboard pytest -q tests` → `83 passed, 2 failed` (apenas as 2 falhas preexistentes de `user_manual` por ausência de `MANUAL.md` na imagem).
  - Checagem de cobertura do `INVENTARIO.md` contra o `grep` → 20/20 arquivos (0 faltando).
  - Checagem das fixtures → `nov2026_mentions.json` com 26 menções e 16 empresas.
- **Pendências:**
  - `uv` e `python3.11` não estão instalados no host Linux atual; `uv sync` não pôde ser executado aqui (ficando para o início do Sprint 1 ou após instalação do `uv`).
  - Os artefatos do Sprint 0 (`plano/INVENTARIO.md`, `pyproject.toml`, `tests/fixtures/baseline/`, atualização do `plano/PLANO.md`) estão pendentes de commit em `feature/modo-local` aguardando autorização do usuário.

---

## Sprint 1: Núcleo sem Airflow e procedimento de upstream

**Objetivo:** importar e executar `src/` (buscadores, hooks, schemas, parsers, utils) num Python comum, sem instalar Airflow e sem editar os arquivos do upstream.

**Tarefas**
1. Criar `compat/airflow_shim/airflow/...` com os módulos e símbolos usados por `src/`, levantados no inventário. Mínimo:
   - `airflow.sdk.Variable.get(key, default=...)`, lendo de um provedor de configuração do Registrale (o SQLite do painel ou um dicionário em memória nos testes);
   - `airflow.sdk.bases.hook.BaseHook` com `get_connection(conn_id)`, devolvendo `host`, `login`, `password`, `port`, `schema` e `extra_dejson` a partir do mesmo provedor (conexões `inlabs_portal` e `inlabs_db`);
   - `airflow.providers.postgres.hooks.postgres.PostgresHook`, implementado com `psycopg`/SQLAlchemy (`get_pandas_df`, `get_sqlalchemy_engine`, `run`);
   - stubs que lancem `NotImplementedError` claro para o que o modo local não usa (DAG, operators, Slack, MSSQL, timetables, `send_email`).
2. Ativação explícita: `compat/bootstrap.py::install_airflow_shim()` insere o shim no `sys.path`, **só** se o Airflow real não estiver instalado.
3. Teste de cobertura do shim, `tests/local/test_shim_imports.py`: importa todos os módulos de `src/` exceto `dou_dag_generator.py`, `dag_load_inlabs/` e `utils/open_search/indexer.py`. Assim, se o upstream passar a usar um símbolo novo do Airflow, esse teste falha.
4. Rodar a suíte de `tests/` aplicável fora do Docker (`uv run pytest -m "not live"`). Marcar com `@pytest.mark.airflow` os testes que exigem Airflow real (geração e carregamento de DAG, e2e) e excluí-los no modo local.
5. Escrever `plano/UPSTREAM.md`:
   - procedimento de merge (`git fetch upstream`, `git merge upstream/main`, conflitos, testes);
   - lista de **patches locais** em arquivos do upstream (arquivo, motivo e trecho), começando pelos já existentes: `searchers.py` (busca por raiz), `hooks/inlabs_hook*.py` (regex de raiz, escape de apóstrofo), `schemas.py` (descarte de itens nulos), `dou_dag_generator.py` (YAML tolerante, DAGs temporárias sem agenda) e `dag_load_inlabs` (manutenção do INLABS, Datasets);
   - lista de **caminhos removidos** (vazia até o Sprint 8).
6. Criar `tools/sync_upstream.py`, que faz fetch e merge sem commit, re-remove os caminhos listados, mantém a nossa versão de `AGENTS.md`/`README.md`, roda os testes locais e imprime o relatório de conflitos. Testar com um merge de ensaio numa branch descartável.
7. Registrar os comandos do modo local na seção 6 do `AGENTS.md`.

**Entregáveis:** `compat/`, testes do shim, `plano/UPSTREAM.md`, `tools/sync_upstream.py`.

**Critério de aceite**
- `uv run pytest -m "not live and not airflow"` passa no Windows e no Linux, sem Airflow instalado.
- `git diff baseline-docker -- src/` não tem mudança feita neste sprint.
- O ensaio de `sync_upstream.py` termina com relatório e sem alterar `main`.

**Riscos:** o upstream pode depender de comportamento interno do Airflow (por exemplo, `Variable.get` com `deserialize_json`). Cubra o shim com testes para cada uso real.

**Registro:**
- **O que foi feito:**
  - Implementado `compat/bootstrap.py` com `install_airflow_shim()`, `is_airflow_installed()` e `uninstall_airflow_shim()`, inserindo `compat/airflow_shim/` no `sys.path` apenas quando o Apache Airflow real não está instalado.
  - Implementado `compat/airflow_shim/airflow/` com os símbolos realmente usados por `src/`:
    - `airflow._provider` (`Connection`, provedores em memória, callback dinâmico, leitura opcional da tabela `settings` via `REGISTRALE_DB_PATH` e fallback `AIRFLOW_VAR_*`);
    - `airflow.sdk.Variable.get` (com `default`, `default_var`, `deserialize_json` e `KeyError`);
    - `airflow.sdk.bases.hook.BaseHook.get_connection` (retornando `host`, `login`, `password`, `port`, `schema`, `conn_type` e `extra_dejson`);
    - `airflow.providers.postgres.hooks.postgres.PostgresHook` sobre `psycopg` e SQLAlchemy (`get_uri`, `get_sqlalchemy_engine`, `get_conn`, `get_pandas_df`, `run`);
    - stubs com `NotImplementedError` explicativo para o que o modo local não usa (`DAG`, `TaskGroup`, `Dataset`, `MsSqlHook`, `SlackNotifier`, `EmptyOperator`, `PythonOperator`, `BranchPythonOperator`, `AssetOrTimeSchedule`, `CronTriggerTimetable` e `send_email`).
  - Criado `tests/local/test_shim_imports.py` cobrindo `install_airflow_shim()`, importação de todos os módulos de `src/` (exceto `dou_dag_generator.py` e `utils/open_search/indexer.py`), `Variable.get`, `BaseHook.get_connection`, `PostgresHook` e todos os stubs `NotImplementedError`.
  - Marcados com `@pytest.mark.airflow` os testes que exigem Airflow real (`test_dag_loading.py`, `test_e2e_dag_execution.py`, `dag_generator_invalid_yaml_test.py` e `test_update_schedule_with_dataset` em `dag_generator_test.py`), mantendo compatibilidade com o modo Docker em `tests/conftest.py` (sem exigir `compat/` dentro do container).
  - Atualizado `pyproject.toml` com dependências faltantes descobertas pelos testes (`pydantic[email]`, `opensearch-py`, `openai`, `anthropic`, `google-genai`, `pendulum`) e `tools/gerador_cli.py` para chamar `install_airflow_shim()` quando executado fora do Docker.
  - Escrito `plano/UPSTREAM.md` com procedimento de merge, tabela dos 8 patches locais existentes em `src/` e `dag_load_inlabs/` e seção de caminhos removidos (vazia até o Sprint 8).
  - Criado `tools/sync_upstream.py` (fetch, `merge --no-commit --no-ff`, preservação `--ours` de `AGENTS.md`/`README.md`, re-remoção de caminhos, execução dos testes locais e relatório).
  - Registrados os comandos do modo local na seção 6 do `AGENTS.md`.
- **Decisões tomadas:**
  - `tests/conftest.py` cria aliases em memória para `dags.ro_dou_src` e `ro_dou_src` apontando para `src/` apenas quando `dags` não está no ambiente, evitando alterar imports dos testes existentes ou copiar `src/`.
  - A ativação do shim em `tests/conftest.py` só roda quando `airflow` real não está instalado, evitando dependência de `compat/` dentro do container Docker.
  - Em `tools/sync_upstream.py`, adicionada a opção `--repo-root` para permitir ensaios isolados em worktrees descartáveis sem sujar a árvore principal.
- **Arquivos criados/alterados:**
  - Criados: `compat/__init__.py`, `compat/bootstrap.py`, `compat/airflow_shim/airflow/__init__.py`, `compat/airflow_shim/airflow/_provider.py`, `compat/airflow_shim/airflow/sdk/__init__.py`, `compat/airflow_shim/airflow/sdk/bases/__init__.py`, `compat/airflow_shim/airflow/sdk/bases/hook.py`, `compat/airflow_shim/airflow/sdk/definitions/__init__.py`, `compat/airflow_shim/airflow/sdk/definitions/asset.py`, `compat/airflow_shim/airflow/providers/__init__.py`, `compat/airflow_shim/airflow/providers/postgres/__init__.py`, `compat/airflow_shim/airflow/providers/postgres/hooks/__init__.py`, `compat/airflow_shim/airflow/providers/postgres/hooks/postgres.py`, `compat/airflow_shim/airflow/providers/microsoft/__init__.py`, `compat/airflow_shim/airflow/providers/microsoft/mssql/__init__.py`, `compat/airflow_shim/airflow/providers/microsoft/mssql/hooks/__init__.py`, `compat/airflow_shim/airflow/providers/microsoft/mssql/hooks/mssql.py`, `compat/airflow_shim/airflow/providers/slack/__init__.py`, `compat/airflow_shim/airflow/providers/slack/notifications/__init__.py`, `compat/airflow_shim/airflow/providers/slack/notifications/slack.py`, `compat/airflow_shim/airflow/providers/standard/__init__.py`, `compat/airflow_shim/airflow/providers/standard/operators/__init__.py`, `compat/airflow_shim/airflow/providers/standard/operators/empty.py`, `compat/airflow_shim/airflow/providers/standard/operators/python.py`, `compat/airflow_shim/airflow/timetables/__init__.py`, `compat/airflow_shim/airflow/timetables/assets.py`, `compat/airflow_shim/airflow/timetables/trigger.py`, `compat/airflow_shim/airflow/utils/__init__.py`, `compat/airflow_shim/airflow/utils/email.py`, `tests/local/test_shim_imports.py`, `plano/UPSTREAM.md`, `tools/sync_upstream.py`.
  - Alterados: `pyproject.toml`, `uv.lock`, `tests/conftest.py`, `tests/pytest.ini`, `tests/dag_generator_test.py`, `tests/dag_generator_invalid_yaml_test.py`, `tests/gerador_cli_test.py`, `tests/test_dag_loading.py`, `tests/test_e2e_dag_execution.py`, `tools/gerador_cli.py`, `AGENTS.md`, `plano/PLANO.md`.
- **Validações:**
  - `git diff baseline-docker -- src/` → vazio (0 alterações em `src/`).
  - Linux (`uv run pytest tests/ -m "not live and not airflow" -q`) → `492 passed, 2 deselected`.
  - Linux completo (`uv run pytest -m "not live and not airflow" -q`) → `577 passed, 2 deselected` (núcleo + painel).
  - Windows 10 VM (`http://127.0.0.1:8006/`, `C:\Registrale-dou`, `uv 0.13.9`, Python 3.11.18):
    - `uv sync --group dev` concluído sem erros (`113` pacotes instalados).
    - `uv run pytest tests/ -m "not live and not airflow" -q` → `492 passed, 2 deselected`.
    - `uv run pytest -m "not live and not airflow" -q` → `577 passed, 2 deselected` (núcleo + painel).
    - Correções de portabilidade Windows descobertas e aplicadas: `os.path.basename` e leitura do objeto de arquivo aberto (`csv_file.seek(0)`) em `tests/dag_generator_test.py`; `sys.stdout/stderr.reconfigure(encoding="utf-8")` em `tools/gerador_cli.py`; `encoding="utf-8"` e `PYTHONIOENCODING=utf-8` em `tests/gerador_cli_test.py`.
  - Docker (`docker exec -w /opt/airflow airflow-scheduler python -m pytest -q tests -m "not live" --ignore=tests/test_e2e_dag_execution.py`) → `456 passed, 1 skipped` (`test_shim_imports.py` pulado por ausência de `compat/` no container).
  - Ensaio de `tools/sync_upstream.py` em worktree descartável (`git worktree add --detach /tmp/registrale-sync-trial HEAD` + `--no-tests`, depois `git worktree remove`) → `Merge exit code: 0`, `Conflitos pendentes (0)`, `main` inalterada (`5415bfc`).
- **Pendências:**
  - Os testes `rodou_dashboard/tests` no modo Docker (`rodou-dashboard`) não foram reexecutados neste sprint pois nenhum arquivo de `rodou_dashboard/` foi alterado.
  - Alterações do Sprint 1 pendentes de commit em `feature/modo-local` aguardando autorização do usuário.

---

## Sprint 2: Executor local (busca DOU) e camada de executor no painel

**Objetivo:** o painel executa rotinas sem o Airflow e produz exatamente as mesmas menções.

**Tarefas**
1. Criar `rodou_dashboard/app/runtime/runner.py`:
   - carrega um YAML com `src/parsers.py`;
   - para cada bloco `search`, chama os buscadores de `src/searchers.py` com os mesmos argumentos que `dou_dag_generator.perform_searches` usa (`reference_date` = data da execução);
   - devolve o mesmo dicionário que hoje vai para o XCom de `exec_search_N` (contrato fixado nas fixtures do Sprint 0).
2. Criar `rodou_dashboard/app/runtime/executor.py` com a interface `Executor`: `trigger(routine, date, **conf) -> run_id`, `status(run_id)`, `wait(run_ids, timeout)`, `result(run_id)`, `pause/unpause(routine)`, `last_runs(routine)`.
   - `AirflowExecutor` encapsula o código atual de `airflow_service.py`, sem mudança de comportamento.
   - `LocalExecutor` roda o runner num `ThreadPoolExecutor` (máximo de 2 rotinas simultâneas e 1 busca por dia por rotina) e grava as execuções na nova tabela `job_runs` (id, rotina, data, status, início, fim, erro, resultado em JSON).
3. Trocar no painel **todas** as chamadas ao Airflow listadas no inventário pela interface (`get_executor()`, escolhido por `REGISTRALE_EXECUTOR`). Estas funções passam a usar `executor.result`:
   - `fetch_mentions_from_dag_run`;
   - `get_last_search_time` / `get_next_search_time`, que hoje leem os logs do Airflow;
   - as "DAGs temporárias" da busca mensal e da busca avulsa (`temp_monthly_dou_*`, `temp_adhoc_dou_*`), que viram execuções do runner com um YAML em memória: nada de arquivo em `dag_confs/` nem descoberta pelo Airflow.
4. Remover do painel o fallback `docker compose exec` (`subprocess`) do `airflow_service`, ou isolá-lo no `AirflowExecutor`.
5. Testes:
   - runner com as fixtures da API do DOU (offline);
   - contrato de resultado comparado com `run_result_*.json`;
   - `LocalExecutor` com concorrência, timeout e erro;
   - **teste de paridade** `tests/local/test_parity_nov2026.py` (`@pytest.mark.live`): roda novembro no modo local e compara o conjunto (CNPJ, data, link) com `nov2026_mentions.json`.

**Entregáveis:** `runtime/runner.py`, `runtime/executor.py`, migração do painel, tabela `job_runs`, testes.

**Critério de aceite**
- Com `REGISTRALE_EXECUTOR=local` e o painel rodando fora do Docker, a busca de data única e a busca mensal de novembro/2026 geram **as mesmas 26 menções de 16 empresas** e o e-mail (via smtp4dev ou SMTP real) é montado igual.
- Com `REGISTRALE_EXECUTOR=airflow`, tudo continua funcionando como antes. Os testes do painel passam nos dois modos.

**Registro:**
- **O que foi feito:**
  - Criado `rodou_dashboard/app/runtime/runner.py` (com `load_specs`, `parse_reference_date`, `run_search_block` e `run_routine`), ativando `compat/bootstrap.py::install_airflow_shim()`, reproduzindo os argumentos de `dou_dag_generator.perform_searches` e devolvendo a lista de dicionários no formato XCom de `exec_search_N`.
  - Criado modelo `JobRun` (`job_runs`: `id`, `rotina`, `data`, `status`, `inicio`, `fim`, `erro`, `resultado_json`) em `rodou_dashboard/app/models.py`.
  - Criado `rodou_dashboard/app/runtime/executor.py` com a interface `Executor`, `AirflowExecutor` (encapsulando `airflow_service.py` e chamadas HTTP/CLI ao Airflow), `LocalExecutor` (`ThreadPoolExecutor(max_workers=2)`, deduplicação por `(rotina, data)` em voo, persistência em `job_runs`), `get_executor_mode()` e `get_executor()` guiados por `REGISTRALE_EXECUTOR`, além de `normalize_date_str`.
  - Migradas para `Executor` todas as chamadas ao Airflow inventariadas em `rodou_dashboard/app/routes/dags.py` (`fetch_mentions_from_dag_run` / `extract_mentions_from_results`, `watch_dag_and_update_mentions`, `trigger_routine`, `run_adhoc_dou_search`, `api_download_missing_inlabs`, `api_trigger_monthly`, `toggle_routine`, `delete_routine`, `configure_main_dag`), `rodou_dashboard/app/routes/admin.py` (`sync_connection`), `rodou_dashboard/app/services/dag_config_service.py` (`get_last_search_time`, `cleanup_orphaned_temp_dags`, `touch_dag_generator`) e `rodou_dashboard/app/services/airflow_service.py` (reexportando `normalize_date_str`).
  - No modo `local`, buscas avulsas (`run_adhoc_dou_search`) e mensais via API DOU (`run_monthly_search_in_background`) executam o YAML em memória via `LocalExecutor.trigger(temp_yaml, ...)`, sem gravar arquivos `temp_*.yaml` em `dag_confs/` e sem tocar `dou_dag_generator.py`.
  - Criados os testes offline `tests/local/test_runner_and_executor.py` (fixtures `dou_api`, contrato `run_result_*.json`, concorrência, deduplicação, timeout, erro e rotas do painel no modo local) e o teste de paridade `live` `tests/local/test_parity_nov2026.py`.
- **Decisões tomadas:**
  - `REGISTRALE_EXECUTOR` mantém `airflow` como padrão enquanto os dois modos convivem (até aprovação do Sprint 7), preservando integralmente o modo Docker e os monkeypatches de `trigger_airflow_dag` nos testes existentes do painel.
  - `LocalExecutor` deduplica disparos simultâneos da mesma `(rotina, data)` retornando o `run_id` ativo em voo e usa `max_workers=2` no `ThreadPoolExecutor`.
  - Timeout da espera da busca mensal na FASE 2 ajustado para `max(1800, 300 * len(dou_run_ids))` após observar que a varredura completa de novembro/2026 (14 dias × 122 CNPJs em 2 workers) levou ~41 min na API do DOU.
- **Arquivos criados/alterados:**
  - Criados: `rodou_dashboard/app/runtime/__init__.py`, `rodou_dashboard/app/runtime/runner.py`, `rodou_dashboard/app/runtime/executor.py`, `tests/local/test_runner_and_executor.py`, `tests/local/test_parity_nov2026.py`.
  - Alterados: `rodou_dashboard/app/models.py`, `rodou_dashboard/app/routes/dags.py`, `rodou_dashboard/app/routes/admin.py`, `rodou_dashboard/app/services/airflow_service.py`, `rodou_dashboard/app/services/dag_config_service.py`, `plano/PLANO.md`.
- **Validações:**
  - `git diff --stat baseline-docker -- src/ dag_load_inlabs/` → vazio (0 alterações em arquivos do upstream).
  - `uv run pytest tests/local/test_runner_and_executor.py -v` → `10 passed` (offline, usando fixtures `dou_api/*` e `run_result_*.json`).
  - `uv run pytest tests/local/test_runner_and_executor.py rodou_dashboard/tests/ -q` → `95 passed` (10 novos do Sprint 2 + 85 do painel no modo `airflow`).
  - Paridade novembro/2026 (`LocalExecutor` + API DOU, 14 dias úteis de 03/11 a 23/11/2026): todos os 14 dias concluíram com `status='success'` em `job_runs`, gerando **26 menções de 16 empresas** com conjunto `(cnpj_norm, data, link)` idêntico ao de `tests/fixtures/baseline/nov2026_mentions.json` (`Faltando: set()`, `Extras: set()`). Montagem do HTML de e-mail (`build_mentions_email_html` + `Relatório Mensal Registrale`, 78.913 bytes, incluindo SURGITEC `24.684.423`) validada com as 26 menções.
- **Pendências:**
  - Envio real de e-mail via `smtp4dev` não foi disparado nesta máquina (validada a montagem do HTML/assunto e o fluxo com `EmailSender` mockado); carga automática do INLABS no modo local fica para o Sprint 4.
  - Reexecução completa de `test_parity_nov2026.py` após aumento do `timeout` para `max(3600, 300 * len(run_ids))` (os dados dos 14 dias já foram validados no `parity.db` da execução anterior).

---

## Sprint 3: Agendador, servidor e ciclo de vida

**Objetivo:** o modo local roda sozinho todos os dias, num processo único e estável no Windows.

**Tarefas**
1. Criar o ponto de entrada `rodou_dashboard/app/runtime/server.py` (`uv run registrale`):
   - sobe o painel com **waitress** (1 processo, 8 threads);
   - inicializa o banco;
   - impede uma segunda instância com lock de arquivo no diretório de dados.
2. Criar `runtime/scheduler.py` com APScheduler (`BackgroundScheduler`, jobstore SQLite, timezone `America/Sao_Paulo`):
   - um job por rotina ativa, com o `schedule` (cron) do YAML, reconstruído quando o YAML muda (o painel já chama `touch_dag_generator`; substituir por `scheduler.reload()`);
   - o agendador do Google Sheets (`start_sheets_scheduler`) passa a ser job do mesmo scheduler, eliminando a duplicação;
   - política de execução perdida: se o PC estava desligado às 8h, executar ao ligar (`misfire_grace_time`, `coalesce=True`), uma vez por dia.
3. Diretório de dados por plataforma (`platformdirs`):
   - `database.db`, `logs/`, `inlabs/` e `rotinas/` (cópia gerenciada de `dag_confs/`);
   - variáveis de ambiente substituem os caminhos fixos (`/data`, `/dag_confs`, `/mnt/airflow-logs`) em `dag_config_service` e afins.
4. Logs em arquivo com rotação (`logs/registrale.log` e `logs/runs/<run_id>.log` por execução), visíveis no painel.
5. Rótulo correto de falhas: erro de SMTP depois da busca vira "Erro Envio E-mail" e não "Erro (Busca Mensal)". As menções continuam gravadas.
6. Rodar no Windows (máquina real ou VM) com `uv run registrale`.

**Entregáveis:** `runtime/server.py`, `runtime/scheduler.py`, diretórios configuráveis, logs.

**Critério de aceite**
- No Windows, sem Docker, o painel abre em `http://localhost:5000`, a rotina principal dispara no horário agendado (teste com um cron de 2 minutos à frente) e a sincronização do Sheets aparece **uma vez** por intervalo.
- Reiniciar o processo não perde agendamentos nem histórico.
- Uma execução perdida com o PC desligado roda ao ligar.

**Registro:**
- **O que foi feito:**
  - Criado `rodou_dashboard/app/runtime/paths.py` com resolução de diretórios por plataforma (`platformdirs.user_data_dir("Registrale", appauthor=False)` no modo `local`, equivalente a `%LOCALAPPDATA%\Registrale` no Windows) e sobrescrita por variáveis de ambiente (`REGISTRALE_DATA_DIR`, `REGISTRALE_DB_PATH`, `REGISTRALE_SCHEDULER_DB_PATH`, `REGISTRALE_LOGS_DIR`, `REGISTRALE_INLABS_DIR`, `REGISTRALE_ROUTINES_DIR`, `SESSION_FILE_DIR`), com cópia inicial de rotinas de `dag_confs/` para `rotinas/` e import lazy de `platformdirs` para compatibilidade com o container Docker legado.
  - Substituídos os caminhos fixos (`/data`, `/dag_confs`, `/mnt/airflow-logs`) por `paths.py` em `rodou_dashboard/app/__init__.py`, `services/dag_config_service.py`, `services/sync_cnpj.py`, `routes/admin.py`, `routes/exports.py` e `routes/dags.py`.
  - Criado `rodou_dashboard/app/runtime/logging_setup.py` com rotação em `logs/registrale.log` (`RotatingFileHandler`, 5 MB × 5 backups), contexto por execução `logs/runs/<run_id>.log` isolado por thread (`LocalExecutor._execute_job`), listagem/leitura segura com proteção contra path traversal e endpoint `GET /api/admin/logs` + aba **Logs do Sistema** em `rodou_dashboard/templates/index.html`.
  - Criado `rodou_dashboard/app/runtime/scheduler.py` (`RegistraleScheduler`) com `APScheduler` (`BackgroundScheduler`, `SQLAlchemyJobStore` em `scheduler_jobs.db`, timezone `America/Sao_Paulo`, `coalesce=True`, `max_instances=1`, `misfire_grace_time=86400`), agendando 1 job por rotina ativa a partir do `schedule` do YAML e unificando o job `sheets_auto_sync` no mesmo agendador (sem iniciar `GoogleSheetsSchedulerThread` no modo `local`). `touch_dag_generator()` e `save_settings` recarregam o agendador em tempo real no modo `local`.
  - Promovida `watch_dag_and_update_mentions` para nível de módulo em `rodou_dashboard/app/routes/dags.py` e ajustado o tratamento de erro SMTP em `watch_dag_and_update_mentions` e `run_monthly_search_in_background` para registrar `"Erro Envio E-mail"` (e nunca `"Erro (Busca Mensal)"` nem `"Busca Concluída"` espúrio), preservando as menções já gravadas.
  - Criado `rodou_dashboard/app/runtime/server.py` (`uv run registrale` via `[project.scripts]` em `pyproject.toml`) com `waitress.serve(..., threads=8)`, inicialização de banco/agendador e lock exclusivo não-bloqueante de instância única (`registrale.lock`, via `msvcrt.locking` no Windows e `fcntl.flock` no POSIX).
  - Criada a suíte offline `tests/local/test_scheduler_and_server.py` (7 testes cobrindo `platformdirs`, lock de instância única, rotação e log por execução, `/api/admin/logs`, carga de rotinas/Sheets no APScheduler, recuperação de misfire após reinício e rótulo `"Erro Envio E-mail"`).
- **Decisões tomadas:**
  - `SQLAlchemyJobStore` utiliza `scheduler_jobs.db` separado de `database.db` para evitar contenção de escrita com o SQLite do Flask-SQLAlchemy, mantendo persistência entre reinícios no diretório de dados.
  - `init_scheduler` chama `start()` antes de `reload()`, e `reload()` preserva jobs cujo cron não mudou, evitando sobrescrever o `next_run_time` persistido para que execuções perdidas disparem ao ligar o PC.
  - Em `paths.py`, `DATA_DIR` do ambiente só é consultado no modo `local` (priorizando `REGISTRALE_DATA_DIR`), evitando colisão com `DATA_DIR=/data` já presente no container Docker `rodou-dashboard`.
- **Arquivos criados/alterados:**
  - Criados: `rodou_dashboard/app/runtime/paths.py`, `rodou_dashboard/app/runtime/logging_setup.py`, `rodou_dashboard/app/runtime/scheduler.py`, `rodou_dashboard/app/runtime/server.py`, `tests/local/test_scheduler_and_server.py`.
  - Alterados: `pyproject.toml`, `rodou_dashboard/app/__init__.py`, `rodou_dashboard/app/runtime/executor.py`, `rodou_dashboard/app/services/dag_config_service.py`, `rodou_dashboard/app/services/sync_cnpj.py`, `rodou_dashboard/app/routes/admin.py`, `rodou_dashboard/app/routes/exports.py`, `rodou_dashboard/app/routes/dags.py`, `rodou_dashboard/templates/index.html`, `plano/PLANO.md`.
- **Validações:**
  - `git diff --stat baseline-docker -- src/ dag_load_inlabs/` → vazio (0 alterações em arquivos do upstream).
  - `uv run pytest tests/local/test_scheduler_and_server.py -v` → `7 passed` (offline).
  - `uv run pytest -m "not live and not airflow" -q` → `594 passed, 3 deselected`.
  - Smoke test `uv run registrale --port 5055` no Linux → `HTTP status: 200` em `/login` e segunda instância bloqueada com exit code `1` (`Outra instância do Registrale já está em execução`).
  - Docker (`docker exec -w /app rodou-dashboard pytest -q tests`) → `81 passed, 4 failed` (as 2 falhas preexistentes de `MANUAL.md` ausente na imagem + 2 falhas pré-existentes de permissão `os.setxattr` ao mover `/tmp/...` para `/data/.env` no container).
- **Pendências:**
  - Execução e captura interativa de `uv run registrale` dentro da VM Windows (`windows-registrale`, `C:\Registrale-dou`) com cron de 2 minutos à frente e verificação visual no navegador `http://localhost:5000` (o agente no Linux não possui shell direto no guest Windows; lock `msvcrt`, `platformdirs` e misfire foram validados por código/testes unitários e o servidor foi validado no Linux).

---

## Sprint 4: INLABS local

**Objetivo:** baixar e pesquisar o INLABS sem Docker, mantendo o modo SQL do upstream.

**Tarefas**
1. `runtime/pg_portable.py`:
   - usa os binários do PostgreSQL 17 para Windows embutidos (`windows/vendor/pgsql/`, sem instalador);
   - no primeiro uso, `initdb` em `%LOCALAPPDATA%\Registrale\pgdata` com senha gerada e guardada no SQLite;
   - `pg_ctl start/stop` atrelado ao ciclo de vida do app, porta livre detectada (padrão 54329) e escuta só em `127.0.0.1`;
   - cria o schema `dou_inlabs` com o `init-db.sql` existente e a extensão `unaccent`.
2. `runtime/inlabs_loader.py`, porta direta das tarefas de `dag_load_inlabs/ro_dou_inlabs_load_pg_dag.py`, reusando a lógica e não reescrevendo:
   - verificação de manutenção do portal, login com reaproveitamento de cookie, listagem e download dos ZIPs do dia;
   - extração **segura** (Zip Slip, limite de tamanho e de quantidade de arquivos);
   - parse dos XML e upsert por `id`;
   - limpeza dos temporários;
   - retenção de 120 dias (`enforce_inlabs_retention_limit` já existe no painel).
3. Conexões `inlabs_portal` e `inlabs_db` servidas pelo shim a partir das configurações do painel (usuário e senha do INLABS já salvos na tela de Integrações).
4. Ligar ao `LocalExecutor`: o download do dia vira job do agendador (horários do upstream: 06:59 e 23:59) e a busca mensal "baixar e pesquisar" usa o loader. A busca INLABS usa `INLABSSQLModeHook` sem mudança.
5. Testes: loader com ZIPs sintéticos (incluindo ZIP malicioso), `pg_portable` (start, stop, porta ocupada) e busca SQL contra o Postgres portátil com artigos sintéticos que cubram as regras de CNPJ por raiz.

**Critério de aceite**
- No Windows: o Postgres portátil sobe e desce com o app.
- Com o portal no ar, baixar um dia e pesquisá-lo gera as mesmas menções que a API do DOU para esse dia (diferenças são documentadas e explicadas).
- Com o portal em manutenção, o fallback para a API do DOU continua.
- **Se o portal estiver em manutenção durante o sprint**, a validação real fica pendente e é registrada; o critério é cumprido com testes sintéticos e revalidado no Sprint 7.

**Registro:**
- **O que foi feito:**
  - Adicionados `get_pgdata_dir()` e `get_pg_bin_dir()` em `rodou_dashboard/app/runtime/paths.py` (suporte a `windows/vendor/pgsql/`, `REGISTRALE_PG_BIN_DIR`, `REGISTRALE_PGDATA_DIR` e fallback no `PATH`).
  - Criado `rodou_dashboard/app/runtime/pg_portable.py` (`PortablePostgres`, `find_free_port`, `start_portable_postgres`, `stop_portable_postgres`) com `initdb` na primeira execução (`%LOCALAPPDATA%\Registrale\pgdata`, senha aleatória gerada via `secrets` e salva no SQLite em `Settings.key='inlabs_pg_config'`), `pg_ctl start/stop` escutando exclusivamente em `127.0.0.1` com detecção automática de porta livre (padrão `54329`), criação do banco `inlabs`, schema `dou_inlabs` via `dag_load_inlabs/sql/init-db.sql` e extensão `unaccent`.
  - Criado `rodou_dashboard/app/runtime/inlabs_loader.py` portando a lógica de `dag_load_inlabs/ro_dou_inlabs_load_pg_dag.py` (`_get_authenticated_session` com reaproveitamento de cookie e falha rápida `InlabsMaintenanceError`, `_find_zip_links`, download, `parse_xml_files`, `upsert_articles` em `dou_inlabs.article_raw`, `check_loaded_data`, limpeza de temporários no `finally`, `record_inlabs_download_success` e `enforce_inlabs_retention_limit(max_days=120)`), com extração ZIP segura (`safe_extract_zip`: proteção contra Zip Slip, symlinks, limite de 2.000 arquivos, 64 MB/arquivo e 512 MB totais).
  - Atualizado `compat/airflow_shim/airflow/_provider.py` para resolver `inlabs_portal` (de `Settings.key='global_settings'` / `INLABS_PORTAL_URL`) e `inlabs_db` (de `INLABS_DB_URL`, `PortablePostgres` ou `Settings.key='inlabs_pg_config'`).
  - Atualizado `rodou_dashboard/app/services/inlabs_service.py` para `get_inlabs_postgres_engine()` usar `PortablePostgres` no modo `local` quando `INLABS_DB_URL` não estiver definida, preservando o comportamento Docker no modo `airflow`.
  - Integrado ao ciclo de vida em `rodou_dashboard/app/runtime/server.py` (start/stop do Postgres portátil), ao `RegistraleScheduler` (`rodou_dashboard/app/runtime/scheduler.py`: job `inlabs_daily_load` com cron `59 6,23 * * *`), ao `LocalExecutor` (`rodou_dashboard/app/runtime/executor.py`: suporte a `ro-dou_inlabs_load_pg`) e às rotas do painel em `rodou_dashboard/app/routes/dags.py` (`api_download_missing_inlabs`, `api_trigger_monthly` FASE 0 e `trigger_routine`, mantendo fallback automático para API DOU quando o portal está em manutenção ou o Postgres portátil está indisponível).
  - Criada a suíte offline `tests/local/test_inlabs_local.py` (12 testes cobrindo porta livre, erro de binários ausentes, `initdb`/start/stop/schema, conexões no shim, extração ZIP segura contra Zip Slip/symlinks/limites, parse XML/deduplicação, manutenção fail-fast, fluxo completo sintético com retenção, regras de CNPJ por raiz no `INLABSSQLModeHook` sem alterar `src/`, job do agendador, `LocalExecutor` e rota de download com manutenção).
- **Decisões tomadas:**
  - `python-slugify` não estava no `pyproject.toml`; `inlabs_loader._slugify_col` usa `slugify` quando instalado e fallback equivalente com `unidecode` + regex, evitando alteração de dependências travadas.
  - Em `PortablePostgres`, quando os binários em `windows/vendor/pgsql/` ou `PATH` não estão presentes (ex.: ambiente Linux sem PostgreSQL instalado ou antes do empacotamento do Sprint 6), o app registra aviso e segue operacional com fallback automático para a API Oficial do DOU.
- **Arquivos criados/alterados:**
  - Criados: `rodou_dashboard/app/runtime/pg_portable.py`, `rodou_dashboard/app/runtime/inlabs_loader.py`, `tests/local/test_inlabs_local.py`.
  - Alterados: `compat/airflow_shim/airflow/_provider.py`, `rodou_dashboard/app/runtime/paths.py`, `rodou_dashboard/app/runtime/server.py`, `rodou_dashboard/app/runtime/scheduler.py`, `rodou_dashboard/app/runtime/executor.py`, `rodou_dashboard/app/services/inlabs_service.py`, `rodou_dashboard/app/routes/dags.py`, `plano/PLANO.md`.
- **Validações:**
  - `git diff --stat baseline-docker -- src/ dag_load_inlabs/` → vazio (0 alterações em arquivos do upstream).
  - `uv run pytest tests/local/test_inlabs_local.py -v -W ignore` → `12 passed in 0.80s`.
  - `uv run pytest -m "not live and not airflow" -q` → `606 passed, 3 deselected` (núcleo + painel + suítes locais).
- **Pendências:**
  - Empacotamento dos binários do PostgreSQL 17 para Windows em `windows/vendor/pgsql/` (escopo do Sprint 6) e validação real de `initdb`/start/stop no Windows e carga/busca real contra o portal INLABS (revalidação no Sprint 7 caso o portal siga em manutenção ou até os binários serem embutidos).
---

## Sprint 5: Arquivo do PDF integral do DOU

**Objetivo:** automatizar o que o analista faz à mão: guardar o PDF integral do DOU de cada dia numa pasta local.

**Tarefas**
1. Investigação (com tempo limitado, registrada no Registro): identificar a fonte oficial do PDF integral por seção e dia (download de PDF da edição no INLABS e/ou leitor do in.gov.br), formato de URL, autenticação, tamanho típico, edições extras e disponibilidade histórica. Escolher a fonte principal e uma alternativa.
2. `runtime/pdf_archiver.py`:
   - baixa os PDFs das seções configuradas para a data;
   - salva em `<pasta>\AAAA\MM\DOU_AAAA-MM-DD_Secao1.pdf` (e extras), de forma idempotente (pula o que já existe e valida tamanho e cabeçalho `%PDF`);
   - tenta de novo quando o portal falha.
3. Agendar junto da busca diária e permitir disparo manual por data e por mês no painel.
4. Tela de configurações: pasta de destino (padrão `Documentos\Registrale\DOU`), seções, ligar/desligar e status do último arquivamento.
5. Cada menção registra o caminho do PDF do dia, para abrir direto da lista de menções.

**Critério de aceite:** num dia útil, os PDFs das seções configuradas aparecem na pasta sem ação do analista, abrem corretamente e são equivalentes aos que ele baixa hoje à mão; rodar de novo não duplica arquivos.

**Fora de escopo (backlog, standby):** exportar só a página com a menção destacada.

**Registro:**
- **Investigação (fontes oficiais de PDF integral do DOU):**
  - **Fonte principal — INLABS (`https://inlabs.in.gov.br/`):** autenticação via `POST /logar.php` (`inlabs_session_cookie` reutilizado com `inlabs_loader.py`); listagem em `GET /index.php?p=AAAA-MM-DD` com download direto por seção em 1 requisição (`AAAA-MM-DD-DO1.pdf`, `DO2.pdf`, `DO3.pdf`, `DO1E.pdf`), tamanho típico ~10–80 MB por seção. Limitações: requer credenciais INLABS, janela de retenção (~120 dias) e encontra-se atualmente em **Manutenção Programada** (HTTP 200 com página `"Manutenção Programada — Imprensa Nacional - INLABS"`).
  - **Fonte alternativa — Portal oficial `pesquisa.in.gov.br` (`INPDFViewer`):** sem autenticação, funciona com INLABS em manutenção e para histórico amplo. Descoberta de edição e contagem de páginas via `GET https://pesquisa.in.gov.br/imprensa/jsp/visualiza/index.jsp?data=DD/MM/AAAA&jornal=<COD>&pagina=1` (`totalArquivos=<N>`; códigos verificados ao vivo em `23/11/2026`: `515`=Seção 1 [228 págs], `529`=Seção 2 [75 págs], `530`=Seção 3 [208 págs], `600`=Edição Extra A [2 págs]; dias sem edição como `20/11/2026` feriado e `22/11/2026` domingo retornam sem `totalArquivos`). Download de cada página em PDF certificado via `GET https://pesquisa.in.gov.br/imprensa/servlet/INPDFViewer?jornal=<COD>&pagina=<P>&data=DD/MM/AAAA&captchafield=firstAccess` (`%PDF-1.4`) e união em PDF único via `pypdf`.
- **O que foi feito:**
  - Adicionado `pypdf==7.1.1` em `pyproject.toml` / `uv.lock`.
  - Criado `get_default_pdf_dir()` em `rodou_dashboard/app/runtime/paths.py` (padrão `Documentos\Registrale\DOU`, com override por `REGISTRALE_PDF_DIR`).
  - Criado `rodou_dashboard/app/runtime/pdf_archiver.py`: arquivamento idempotente em `<pasta>/<AAAA>/<MM>/DOU_<AAAA-MM-DD>_SecaoN.pdf`, validação de tamanho mínimo, cabeçalho `%PDF` e estrutura via `pypdf`, escrita atômica via `.tmp`, retries com backoff, fallback automático de INLABS para `pesquisa.in.gov.br`, arquivamento por data e por mês (`archive_date_pdfs`, `archive_month_pdfs`), status persistido em `Settings` (`pdf_archive_status`) e vínculo automático com menções (`resolve_pdf_for_mention`, `link_mentions_to_pdfs`).
  - Agendador (`rodou_dashboard/app/runtime/scheduler.py`): `_run_scheduled_pdf_archive()` executa automaticamente após a busca diária de `Pesquisa_cnpj.yaml` quando habilitado.
  - Banco e rotas (`models.py`, `__init__.py`, `routes/admin.py`, `routes/auth.py`, `routes/dags.py`): coluna `Mention.pdf_path` com migração segura `ALTER TABLE`, configuração `global_settings.pdf_archive`, endpoints `GET /api/pdf_archive/status`, `POST /api/pdf_archive/run` (por data ou mês) e `GET /api/pdf_archive/open` (com proteção contra path traversal).
  - Interface (`rodou_dashboard/templates/index.html`): sub-aba **Arquivo PDF DOU** em Configurações (ligar/desligar, pasta de destino, seções, status do último arquivamento, disparo manual por data e por mês) e botão **"Abrir PDF Integral do Dia"** na tabela de menções.
- **Decisões tomadas:**
  - `pypdf` escolhido por ser puro Python, leve e sem dependências nativas para facilitar o empacotamento Windows no Sprint 6.
  - Fallback automático para `pesquisa.in.gov.br` garante funcionamento imediato mesmo com o INLABS em manutenção programada.
  - `src/` e `dag_load_inlabs/` não foram alterados (nenhum patch novo em `plano/UPSTREAM.md`).
- **Arquivos criados/alterados:** `pyproject.toml`, `uv.lock`, `rodou_dashboard/app/runtime/paths.py`, `rodou_dashboard/app/runtime/pdf_archiver.py`, `rodou_dashboard/app/runtime/scheduler.py`, `rodou_dashboard/app/models.py`, `rodou_dashboard/app/__init__.py`, `rodou_dashboard/app/routes/admin.py`, `rodou_dashboard/app/routes/auth.py`, `rodou_dashboard/app/routes/dags.py`, `rodou_dashboard/templates/index.html`, `tests/local/test_pdf_archiver.py`, `plano/PLANO.md`.
- **Validações:**
  - `uv run pytest tests/local/test_pdf_archiver.py -m "not live" -v` → `6 passed, 1 deselected`.
  - `uv run pytest tests/local/test_pdf_archiver.py -m "live" -v` → `1 passed` (download real da Edição Extra A de `23/11/2026`, 2 páginas válidas via `pesquisa.in.gov.br`).
  - `uv run pytest -m "not live and not airflow" -q` → `612 passed, 4 deselected`.
- **Pendências:**
  - Validação visual do fluxo no navegador/Windows e download ao vivo via INLABS quando o portal sair de manutenção programada (revalidação no Sprint 7).
---

## Sprint 6: Instalador Windows

**Objetivo:** instalação de um clique e uso diário sem terminal.

**Tarefas**
1. `windows/build.ps1`, script de build reprodutível:
   - baixa o Python 3.11 *embeddable* (versão fixa, com hash verificado) e instala as dependências travadas (`uv export` → `pip install --target`);
   - copia o app (`rodou_dashboard/`, `src/`, `compat/`, `dag_confs/`) e o PostgreSQL portátil;
   - gera `Registrale-Setup-<versão>.exe` com Inno Setup (`windows/installer.iss`).
2. Launcher `windows/launcher.pyw`:
   - ícone na bandeja com os itens Abrir painel, Status, Ver logs, Reiniciar e Sair;
   - sobe o servidor sem janela de console e abre o navegador;
   - atalho no Menu Iniciar e na Área de Trabalho, e início automático com o Windows (atalho em `shell:startup`, opcional no instalador).
3. Primeira execução:
   - assistente que **importa os dados atuais**: `data/database.db` do modo Docker (empresas, menções, configurações e templates) e rotinas de `dag_confs/`;
   - o backup é feito antes da importação.
4. Atualização:
   - o painel consulta as Releases do repositório e oferece "Atualizar";
   - o instalador novo preserva `%LOCALAPPDATA%\Registrale`;
   - migrações de banco versionadas (tabela `schema_version`).
5. Desinstalação mantém os dados, salvo se o usuário marcar a remoção.
6. CI: workflow `windows-build.yml` (runner `windows-latest`) que roda os testes do modo local, gera o instalador e publica o artefato com hash SHA-256 (publicação de release só com pedido do usuário).

**Critério de aceite:** numa VM Windows 10/11 limpa:
- instalar, abrir pelo atalho, importar o banco atual, ver as mesmas empresas e menções, rodar uma busca e receber o e-mail;
- reiniciar o Windows e o app volta sozinho;
- instalar a versão seguinte por cima preserva os dados.

**Registro:**
- **O que foi feito:**
  - Versionamento e migrações (`rodou_dashboard/app/runtime/version.py` e `rodou_dashboard/app/runtime/migrations.py`): leitura de versão semântica (`get_app_version`, `parse_version`, `is_newer_version`) e tabela `schema_version` com runner idempotente `apply_migrations(db.engine)` integrado ao `create_app()` em `rodou_dashboard/app/__init__.py` (migrações v1: `mentions.pdf_path` + índices; v2: índices de `job_runs`).
  - Assistente de primeira execução (`rodou_dashboard/app/runtime/migrator.py`): `backup_database()` via API `sqlite3.backup()` em `backups/database.db.bak-<timestamp>`, `detect_legacy_sources()`, `import_docker_database()` (empresas, menções, configurações, templates de e-mail, histórico, usuários e log INLABS, com proteção contra duplicatas) e `import_routines_from_dir()` (filtrando `temp_*`, `*_part_*`, `*_sync*`).
  - Atualizador via GitHub Releases (`rodou_dashboard/app/runtime/updater.py`): `check_for_updates()` consultando `/releases/latest` (padrão `Yaddz/Registrale-dou`, configurável por `REGISTRALE_GITHUB_REPO`), `verify_sha256()` e `download_and_verify_update()` com validação estrita de host HTTPS (`github.com` / `*.githubusercontent.com`), verificação obrigatória de hash SHA-256 antes de renomear `.tmp` e `launch_installer_windows()`.
  - Rotas e UI (`rodou_dashboard/app/routes/admin.py`, `rodou_dashboard/templates/index.html`): endpoints `GET /api/admin/first_run_status`, `POST /api/admin/first_run_import`, `GET /api/admin/updates/check`, `POST /api/admin/updates/download` e sub-aba **Sistema & Atualizações** em Configurações (importação de `database.db`/rotinas detectadas ou por upload + verificação e download de atualizações).
  - Empacotamento e launcher Windows (`windows/registrale.ico`, `windows/launcher.pyw`, `windows/build.ps1`, `windows/installer.iss`, `pyproject.toml` grupo `windows`, `uv.lock`):
    - `windows/launcher.pyw`: ícone na bandeja (`pystray`) com **Abrir painel**, **Status**, **Ver logs**, **Reiniciar** e **Sair**, iniciando `rodou_dashboard.app.runtime.server` sem console (`CREATE_NO_WINDOW`) e abrindo o navegador.
    - `windows/build.ps1`: baixa Python `3.11.9` embeddable com SHA-256 verificado (`009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b`), exporta dependências travadas (`uv export --frozen --group windows`), copia app + PostgreSQL 17 portátil (`windows/vendor/pgsql/` ou download) e gera `dist/Registrale-Setup-<versão>.exe` + `.sha256` via Inno Setup 6.
    - `windows/installer.iss`: instala em `{localappdata}\Programs\Registrale`, cria atalhos no Menu Iniciar, Área de Trabalho e `shell:startup` (`--no-browser`), fecha processos em atualização e preserva `{localappdata}\Registrale` na atualização e na desinstalação (só remove se o usuário confirmar explicitamente no diálogo).
  - CI (`.github/workflows/windows-build.yml`): workflow em `windows-latest` que roda `uv run pytest -m "not live and not airflow" -q`, compila o instalador via `windows\build.ps1` e publica `Registrale-Setup-*.exe` + `.sha256` como artefato do workflow (sem publicar Release automaticamente).
  - Testes offline (`tests/local/test_windows_packaging.py`): 10 testes cobrindo versionamento, `schema_version` idempotente, backup + importação de banco e rotinas, verificação SHA-256 e bloqueio de host não confiável no updater, rotas admin e `RegistraleTrayController` + validação estrutural dos artefatos Windows.
- **Decisões tomadas:**
  - Dependências exclusivas de bandeja (`pystray`, `pillow`) isoladas no grupo `windows` do `pyproject.toml`, evitando impacto no container Docker legado e na instalação headless.
  - `os.environ.setdefault("REGISTRALE_EXECUTOR", "local")` mantido dentro de `main()` (e no `env` do subprocesso) em `windows/launcher.pyw`, evitando mutação global de ambiente ao importar o módulo.
  - `src/` e `dag_load_inlabs/` não foram alterados (nenhum patch novo em `plano/UPSTREAM.md`).
- **Arquivos criados/alterados:**
  - Criados: `rodou_dashboard/app/runtime/version.py`, `rodou_dashboard/app/runtime/migrations.py`, `rodou_dashboard/app/runtime/migrator.py`, `rodou_dashboard/app/runtime/updater.py`, `windows/registrale.ico`, `windows/launcher.pyw`, `windows/build.ps1`, `windows/installer.iss`, `.github/workflows/windows-build.yml`, `tests/local/test_windows_packaging.py`.
  - Alterados: `pyproject.toml`, `uv.lock`, `rodou_dashboard/app/__init__.py`, `rodou_dashboard/app/routes/admin.py`, `rodou_dashboard/templates/index.html`, `plano/PLANO.md`.
- **Validações:**
  - `git diff --stat baseline-docker -- src/ dag_load_inlabs/` → vazio (0 alterações em arquivos do upstream).
  - `uv run pytest tests/local/test_windows_packaging.py -v` → `10 passed in 0.34s`.
  - `uv run pytest -m "not live and not airflow" -q` → `622 passed, 4 deselected`.
- **Pendências:**
  - Execução real do `windows/build.ps1` no `windows-latest` / Windows 10/11 e validação interativa numa VM Windows limpa (instalação via `Registrale-Setup-*.exe`, importação do banco atual, busca + e-mail, reinício do Windows com auto-start e atualização por cima preservando `%LOCALAPPDATA%\Registrale`), pois o ambiente de execução atual é Linux sem Inno Setup / VM Windows acessível por shell.
---

## Sprint 6.1: Contingência INLABS (prioritário, fora da ordem)

**Motivo:** o portal INLABS está em "Manutenção Programada" há mais de um mês. A rotina principal usa `sources: [INLABS]`; a busca agendada do modo local disparava a rotina direto, sem fallback, e pesquisava um banco vazio (zero menções, sem erro visível). Só os disparos manuais e a mensal caíam para a API do DOU (lenta: ~3 min/dia para 122 CNPJs, com timeouts).

**Solução:** fonte alternativa de texto integral sem INLABS: o PDF do DOU de `pesquisa.in.gov.br`, o mesmo que o Sprint 5 já arquiva na pasta do analista.

**Registro:**
- **Revisão dos Sprints 2–6 (achados):**
  - **Crítico, corrigido:** fora do pytest o runner não importava `src/searchers.py` (`ModuleNotFoundError: ro_dou_src`): o upstream importa `ro_dou_src.utils.open_search.*` em `hooks/inlabs_hook.py` e o alias só existia em `tests/conftest.py`. O modo local quebraria em produção em toda rotina. `runner._ensure_src_imports` agora cria o alias; teste em subprocesso `test_default_searchers_import_outside_pytest`.
  - **Crítico, corrigido:** busca agendada (`scheduler._run_scheduled_routine`) sem fallback do INLABS → agora o próprio runner decide a fonte por bloco, o que cobre agendada, manual, mensal e avulsa.
  - **Médio, pendente:** no modo Docker o agendamento é do Airflow, que segue pesquisando o INLABS vazio; enquanto o analista usar Docker, só os disparos pelo painel caem para a API.
  - **Baixo, pendente:** as mensagens do histórico ainda dizem "via API Oficial do DOU" quando o modo local usa o PDF; `pdf_archiver.normalize_section_key` não reconhece `SECAO_1` (o `pdf_search` tem o próprio mapeamento); sem tela para `inlabs_fallback` (só `global_settings` e variável de ambiente).
  - **Observação:** o download usa `INPDFViewer?...&captchafield=firstAccess`, a mesma URL pública do visualizador. Se o portal passar a exigir captcha, **não contornar**: cair para a API do DOU (já é o comportamento em caso de falha).
- **O que foi feito:**
  - `rodou_dashboard/app/runtime/pdf_search.py`: garante os PDFs do dia (`archive_date_pdfs`, na pasta do arquivo ou em `<dados>/pdf_cache` se o arquivo estiver desligado), extrai o texto por página com cache gzip em `<dados>/pdf_text`, normaliza números quebrados em linha (`0001-\n36`), procura cada empresa com `utils.cnpj.find_company_mentions` (mesma regra de raiz) e monta publicações no formato XCom com trecho destacado, título do ato e link para a página no visualizador oficial.
  - Confirmação na API do DOU **só para as empresas achadas** (poucas requisições em vez de 122): quando a API acha, usa a publicação dela (link e título da matéria, idêntico à baseline); senão fica o link da página do PDF.
  - Seções cujo PDF falhou são completadas pela API do DOU; PDF indisponível → API com todos os termos.
  - `runtime/runner.py`: `_use_inlabs_fallback` / `_run_inlabs_fallback` / `_merge_term_results`; `INLABS_FALLBACK` incluído nos buscadores padrão.
  - `routes/dags.py`: `_fallback_sources()` → buscas avulsa e mensal do modo local passam pelo runner com `INLABS` (que cai para o PDF); `api_dou_only` e modo Airflow continuam na API.
  - Testes: `tests/local/test_pdf_search.py` (14 offline) e `tests/local/conftest.py` (suítes offline usam `api` para não baixar PDFs reais).
- **Validações:**
  - Varredura do PDF (03, 09 e 23/11/2026, 122 CNPJs): 15/15 pares empresa/dia da baseline, 0 extras; nos casos "só raiz" da API o PDF traz o CNPJ completo.
  - Ponta a ponta, runner real sem INLABS, rotina `Pesquisa_cnpj.yaml` (04 e 16/11/2026): 8/8 menções com **links idênticos** à baseline, 0 extras; 130 s e 167 s por dia, incluindo download (~75 s) e extração.
  - `uv run pytest -m "not live and not airflow" -q` → `636 passed`.
- **O que foi feito (conclusão das tarefas 1–7):**
  - **Fonte efetiva no `runner`, `job_runs` e histórico (tarefa 1):** `runtime/runner.py` (`_run_inlabs_fallback` e `run_search_block`) agora registra `source_used` (`"INLABS"`, `"PDF integral + API do DOU"`, `"API do DOU"` / `"API Oficial do DOU"`, `"QD"`, `"DOESP"`) em cada bloco do resultado (persistido em `JobRun.resultado_json`). `routes/dags.py` (`_describe_local_fallback_source`, `_extract_sources_used_from_runs`, `watch_dag_and_update_mentions`, `trigger_routine` e `api_trigger_monthly`) passou a exibir a fonte real nas mensagens e no `SyncHistory` (`[Fonte: ...]`).
  - **Configuração na tela (tarefa 2):** `routes/auth.py` (`index`), `routes/admin.py` (`get_settings`, `save_settings` com validação `{pdf, api, off}`) e `templates/index.html` (card INLABS em Configurações → Integrações) adicionaram o seletor **"Fonte quando o INLABS estiver fora"** (`inlabs_fallback`) com descrição de cada opção.
  - **Aviso visível no painel (tarefa 3):** `routes/admin.py::api_status()` retorna `inlabs_status` (`portal_ok`, `portal_message`, `today_loaded`, `fallback_mode`, `fallback_label`, com cache de 60 s para o portal), e `templates/index.html` exibe banner de alerta no topo da aba inicial quando o INLABS está fora/em manutenção ou sem a edição do dia, indicando a fonte de contingência ativa.
  - **Mapeamento único de seções (tarefa 4):** `pdf_archiver.normalize_section_key()` passou a aceitar os identificadores do YAML (`SECAO_1`, `SECAO_2`, `SECAO_3`, `EDICAO_EXTRA`, `EDICAO_SUPLEMENTAR` e enums) e `pdf_search.section_keys_from_dou_sections()` delega diretamente para ele.
  - **Teste `live` do fallback (tarefa 5):** `tests/local/test_pdf_search.py::test_live_fallback_pdf_matches_baseline_day` executa `run_routine` em `dag_confs/Pesquisa_cnpj.yaml` para `2026-11-16` com `REGISTRALE_INLABS_FALLBACK=pdf` e `INLABS_HAS_DATE=False`, confirmando `source_used == "PDF integral + API do DOU"` e igualdade exata de `(cnpj_norm, link)` com `tests/fixtures/baseline/nov2026_mentions.json`.
  - **Smoke fora do pytest no CI Windows (tarefa 6):** `.github/workflows/windows-build.yml` executa `_build_default_searchers()` via `python -c` e sobe `uv run registrale --port 5099` verificando HTTP 200 em `/login`.
  - **Documentação Docker (tarefa 7):** `AGENTS.md` (seção 3, item 6) e `README.md` documentam o procedimento de contingência no modo Docker (trocar a fonte de `Pesquisa_cnpj.yaml` para API do DOU pelo painel e restaurar para INLABS quando o portal retornar), sem alterar o Airflow.
- **Arquivos criados/alterados (conclusão):** `rodou_dashboard/app/runtime/pdf_archiver.py`, `rodou_dashboard/app/runtime/pdf_search.py`, `rodou_dashboard/app/runtime/runner.py`, `rodou_dashboard/app/routes/dags.py`, `rodou_dashboard/app/routes/admin.py`, `rodou_dashboard/app/routes/auth.py`, `rodou_dashboard/templates/index.html`, `.github/workflows/windows-build.yml`, `AGENTS.md`, `README.md`, `tests/local/test_pdf_search.py`, `tests/local/test_runner_and_executor.py`, `plano/PLANO.md`.
- **Validações finais:**
  - `git diff --stat baseline-docker -- src/ dag_load_inlabs/` → vazio (0 alterações em arquivos do upstream).
  - `uv run pytest tests/local/test_pdf_search.py -m "not live" -v` → `18 passed, 1 deselected`.
  - `uv run pytest tests/local/test_pdf_search.py -m "live" -v` → `1 passed` (`2026-11-16` idêntico à baseline).
  - `uv run pytest -m "not live and not airflow" -q` → **`640 passed, 5 deselected`**.
- **Pendências:**
  - Rodar a paridade do mês inteiro (`test_parity_nov2026.py`) com `REGISTRALE_INLABS_FALLBACK=pdf` no Sprint 7; validar o smoke no runner `windows-latest` e em VM Windows 10/11.

**Tarefas restantes do 6.1 (prompt [`prompts/sprint-6.1.md`](prompts/sprint-6.1.md))**
1. Histórico e mensagens do painel dizem qual fonte foi usada de fato ("INLABS", "PDF integral + API do DOU", "API do DOU"); hoje o modo local diz "via API Oficial do DOU" mesmo usando o PDF. A fonte usada fica também no resultado de `job_runs`.
2. Tela de Configurações: seletor "Fonte quando o INLABS estiver fora" (`inlabs_fallback`: PDF integral / API do DOU / Desligado), com texto explicando cada opção.
3. Aviso visível no painel quando o INLABS está em manutenção ou sem o dia (status do portal + fonte em uso).
4. `pdf_archiver.normalize_section_key` aceita os nomes do YAML (`SECAO_1`, `EDICAO_EXTRA`); um mapeamento só para as duas partes (`pdf_search` e `pdf_archiver`).
5. Teste `live` do fallback: `run_routine` de um dia da baseline com `REGISTRALE_INLABS_FALLBACK=pdf` sem INLABS → menções e links idênticos.
6. Smoke **fora do pytest** no CI do Windows: `python -c` que importa `_build_default_searchers()` e sobe `registrale --port` respondendo `/login` (o alias `ro_dou_src` só falhava fora do pytest).
7. Modo Docker (enquanto existir): **não** mudar o Airflow. Documentar no README/AGENTS o procedimento de contingência: trocar a fonte da rotina principal para API do DOU pelo painel enquanto o INLABS estiver fora, e voltar depois.

**Critério de aceite do 6.1:** itens 1–6 com testes offline; 636+ testes passando; `src/` e `dag_load_inlabs/` sem alterações; revisão independente aprovada.

---

## Sprint 7: Validação de paridade 100% e homologação

**Objetivo:** provar que o modo local substitui o Docker sem perda e obter a aprovação do usuário.

**Checklist (todos obrigatórios, com evidência no Registro)**
1. Paridade de busca, local × Docker, para a mesma rotina e as mesmas datas:
   - novembro/2026 completo (26 menções, 16 empresas);
   - um segundo mês completo escolhido pelo usuário;
   - 5 buscas de data única.
   
   Divergência zero, ou cada diferença explicada e aceita pelo usuário.
2. Fonte sem INLABS (contingência do Sprint 6.1), **obrigatória**:
   - novembro/2026 completo com `REGISTRALE_INLABS_FALLBACK=pdf` e sem INLABS → 26 menções, 16 empresas, links iguais à baseline;
   - o mesmo mês com `api` → mesmo resultado (as duas contingências batem);
   - busca agendada real no modo local, com o INLABS fora, gerando menções e e-mail.
3. INLABS real: pelo menos 3 dias baixados e pesquisados no modo local com o portal no ar, comparados à API do DOU. **Não bloqueia a homologação** enquanto o portal estiver em manutenção: fica registrado em `HOMOLOGACAO.md` como pendência aceita pelo usuário, a validar quando o portal voltar (a carga e a busca INLABS têm testes offline do Sprint 4).
4. Agendamento: 5 dias úteis seguidos de execução automática no PC do analista, sem intervenção, com e-mails recebidos.
5. PDFs: 5 dias úteis arquivados automaticamente (os mesmos usados pela busca de contingência).
6. Resiliência:
   - portal do DOU lento ou fora (timeouts);
   - INLABS em manutenção (busca cai para o PDF sem intervenção);
   - `pesquisa.in.gov.br` fora ou PDF de uma seção falhando (seção completada pela API do DOU);
   - portal pedindo captcha no visualizador: **não contornar**; confirmar que cai para a API do DOU;
   - SMTP errado (menções gravadas, erro rotulado certo);
   - PC desligado no horário;
   - duas buscas simultâneas.
7. Instalação, atualização e desinstalação numa VM limpa (critério do Sprint 6).
8. Upstream: ensaio de `tools/sync_upstream.py` com o `upstream/main` do momento; os testes do modo local passam.
9. Desempenho: RAM em repouso abaixo de 400 MB, abertura em menos de 15 s, busca diária pelo PDF em menos de 5 min e busca mensal comparável ao modo Docker.
10. Execução real fora do pytest: o app instalado roda a rotina principal de ponta a ponta (lição do alias `ro_dou_src`, que só quebrava fora dos testes).

**Entregável:** `plano/HOMOLOGACAO.md` com resultados, evidências e o termo **"Aprovado para remover Docker/Airflow"** assinado pelo usuário (registro de quem aprovou e quando).

**Registro:**
- **O que foi feito:**
  - Criado `plano/HOMOLOGACAO.md` com a tabela completa `item → resultado → evidência` cobrindo todos os 10 itens do checklist do Sprint 7 e a regressão do modo Docker.
  - Validada paridade 100% de novembro/2026 completo (03–23/11/2026, 14 dias úteis) nos dois modos de contingência:
    - API Oficial do DOU (`uv run pytest tests/local/test_parity_nov2026.py -m "live" -v` → `1 passed in 1270.66s`): **26 menções, 16 empresas**, conjunto `(cnpj_norm, data, link)` idêntico à baseline Docker (`tests/fixtures/baseline/nov2026_mentions.json`).
    - PDF integral (`REGISTRALE_INLABS_FALLBACK=pdf`, `INLABS_HAS_DATE=False`, 14 dias úteis → `961.9 s`): **26 menções, 16 empresas**, `sources=['PDF integral + API do DOU']`, `missing=set()`, `extra=set()`.
  - Validadas 5 buscas de data única (`2026-11-03`, `2026-11-04`, `2026-11-13`, `2026-11-19`, `2026-11-23`) no modo local contra a baseline Docker: 5/5 com `match=True`.
  - Validado fluxo agendado + e-mail SMTP real (`RegistraleScheduler` + `LocalExecutor` + `watch_dag_and_update_mentions` em `2026-11-23`, modo `PDF integral + API do DOU`): `4` menções gravadas, `SyncHistory` `"E-mail Enviado ... [Fonte: PDF integral + API do DOU]"` e e-mail SMTP recebido (`21.320 bytes`).
  - Validada resiliência (suíte offline `640 passed, 5 deselected` + verificação direta de rejeição de HTML/captcha sem contorno em `pdf_archiver._download_pesquisa_page`), desempenho (`0,51 s` de abertura, `67,0 MB` de RAM em repouso em `.venv/bin/registrale`), execução fora do pytest (`_build_default_searchers()` e `/login` HTTP 200) e ensaio de upstream (`tools/sync_upstream.py` → `Merge exit code: 0`, `0` conflitos).
  - Verificado que o portal INLABS (`https://inlabs.in.gov.br/`) segue em `"Manutenção Programada"`, registrando o item 3 como pendência não bloqueante em `plano/HOMOLOGACAO.md`.
- **Decisões tomadas:**
  - Nenhuma alteração em `src/`, `dag_load_inlabs/` ou no código do painel foi necessária durante a validação (0 defeitos encontrados nos fluxos validados); apenas os documentos de homologação e registro foram criados/atualizados.
  - Item 3 (INLABS real) mantido como pendência não bloqueante conforme regra do plano, aguardando aceite do usuário para seguir sem ele até o portal retornar.
- **Arquivos criados/alterados:**
  - Criado: `plano/HOMOLOGACAO.md`.
  - Alterado: `plano/PLANO.md`.
- **Validações:**
  - `uv run pytest -m "not live and not airflow" -q` → `640 passed, 5 deselected`.
  - `uv run pytest tests/local/test_parity_nov2026.py -m "live" -v` → `1 passed in 1270.66s` (26 menções, 16 empresas).
  - Paridade novembro/2026 `REGISTRALE_INLABS_FALLBACK=pdf` → `26` menções, `16` empresas, `missing=set(), extra=set()` em `961.9 s`.
  - 5 datas únicas (`03, 04, 13, 19, 23/11/2026`) → 5/5 `match=True` (`5.13 s` a `11.46 s` com cache).
  - Docker `airflow-scheduler` (`pytest -q tests -m "not live" --ignore=tests/test_e2e_dag_execution.py --ignore=tests/local`) → `456 passed`.
  - Docker `rodou-dashboard` (`pytest -q tests`) → `81 passed, 4 failed` (4 falhas preexistentes do container).
  - `tools/sync_upstream.py --repo-root /tmp/registrale-sync-s7 --no-tests` → `Merge exit code: 0`, `0` conflitos.
  - `.venv/bin/registrale --port 5058` (Linux): abertura em `0,51 s`, RAM em repouso `67,0 MB`, HTTP 200 em `/login`.
  - VM Windows 10 (`windows-registrale`):
    - `uv run pytest -m "not live and not airflow" -q` → `640 passed, 5 deselected` em `112.10s`.
    - `windows\build.ps1 -SkipPostgresDownload` (Inno Setup 6.7.4) → `Registrale-Setup-0.1.0.exe` (`62.564.996` bytes, SHA-256 `afefa91f5db3f5edd373760a8ffa714bcfe3233a4e62a38a272b236029680785`).
    - App instalado: abertura em `10,71 s` (`HTTP 200` em `/login`), RAM total `127,3 MB` (`python.exe` `66 MB` + `pythonw.exe` `61,3 MB`), atalhos Desktop e Startup criados.
    - Execução ponta a ponta no `python.exe` embeddable instalado (`Pesquisa_cnpj.yaml`, `2026-11-23`, fallback PDF) → `WIN_E2E_OK=True status=success mentions=4 elapsed=143.8s roots=['05785287', '07021336', '09217325', '24684423']`.
    - Desinstalação (`unins000.exe`) e reinstalação por cima → programa removido/reinstalado e `%LOCALAPPDATA%\Registrale\database.db` (`114.688` bytes) preservado em ambas.
- **Pendências (dependem do usuário / PC do analista):**
  - ~~Item 1b~~: outubro/2026 (16 empresas) validado em 24/11/2026: Docker, local API e local PDF → 18 menções, 9 empresas, sem divergência.
  - ~~Item 3~~ e ~~itens 4 e 5~~: aceitos pelo usuário como pendência em 24/11/2026 (registrado em `plano/HOMOLOGACAO.md`); validar INLABS quando o portal voltar e acompanhar os primeiros dias de uso real.
  - ~~Assinatura do termo~~: "Aprovado para remover Docker/Airflow" assinado em `plano/HOMOLOGACAO.md` em 24/11/2026 (Pedro, via chat).
  - ~~Revisão independente~~: Sprint 7 aprovado em 24/11/2026, sem bloqueadores.
  - ~~Pré-condições do Sprint 8 vindas da revisão~~: estado homologado commitado em `4f68dc6` (pedido do usuário, 24/11/2026) e ensaio de `tools/sync_upstream.py` refeito com testes → `640 passed` (`upstream/main` sem commits novos desde `4ebffba`).
---

## Sprint 8: Remoção de Docker/Airflow, limpeza do git e novo README

**Pré-condição:** aprovação registrada em `plano/HOMOLOGACAO.md` (assinada em 24/11/2026), revisão do Sprint 7 aprovada e **o estado homologado commitado** (ponto de retorno antes de apagar arquivos). Sem isso, este sprint não começa.

**Tarefas**
1. Remover Docker, Airflow e Kubernetes:
   - `Dockerfile`, `docker-compose*.yml`, `.dockerignore`, `Makefile`, `Makefile.backup`, `generate-Makefile.sh`, `instalar.bat`, `helm/`, `k8s/`, `docs/Dockerfile` e `docs/docker-compose.yml`;
   - `src/dou_dag_generator.py` e `dag_load_inlabs/` (lógica já portada para `runtime/inlabs_loader.py`; mover `dag_load_inlabs/sql/init-db.sql` para `rodou_dashboard/app/runtime/sql/` e atualizar `pg_portable._read_init_sql`);
   - **não remover** `src/utils/open_search/`: `src/hooks/inlabs_hook.py` do upstream o importa;
   - testes exclusivos do Airflow (`@pytest.mark.airflow`);
   - `rodou_dashboard/Dockerfile`, `AirflowExecutor`, `airflow_service.py` e `REGISTRALE_EXECUTOR`, que passa a ser sempre local;
   - ramos do modo Airflow em `routes/dags.py` (ex.: `_fallback_sources` passa a só consultar `inlabs_fallback`), mantendo a contingência PDF → API do Sprint 6.1;
   - workflows de CI de Docker e Helm.
2. Atualizar `plano/UPSTREAM.md` com a lista final de **caminhos removidos** e validar `tools/sync_upstream.py` contra o `upstream/main`: o merge re-remove esses caminhos e os testes passam.
3. Limpeza do git, com confirmação do usuário a cada item destrutivo:
   - remover a worktree `Registrale-dou-sync` e a branch `upstream-sync` (já mergeada);
   - remover o stash `backup-pre-merge`;
   - remover os containers `sync-*` e as imagens antigas;
   - revisar o `.gitignore` (dados, build do Windows, `vendor/`);
   - remover arquivos de teste e rascunhos versionados por engano;
   - integrar `feature/modo-local` em `main` e criar a tag `v1.0.0`.
4. Reescrever o `README.md`: o que é, requisitos (Windows 10/11), instalação pelo `.exe`, primeiro uso (importação, integrações, planilha), uso diário, onde ficam dados, logs e PDFs, atualização do app, como receber atualizações do Ro-DOU (link para `plano/UPSTREAM.md`) e créditos e licença do Ro-DOU.
5. Atualizar o `AGENTS.md` para o estado pós-migração: remover as seções do modo Docker e a convivência dos dois modos.
6. Atualizar os manuais do painel (`rodou_dashboard/docs/`, `MANUAL.md`) que citam Docker, Airflow ou `make`.

**Critério de aceite**
- `grep -rni "docker\|airflow\|helm\|make run" --exclude-dir=.git` só retorna o shim (`compat/airflow_shim`, `compat/bootstrap.py`), o alias `ro_dou_src` e seus comentários em `runtime/runner.py`, o código do upstream em `src/` (imports do shim), o histórico (`CHANGELOG.md`) e a seção de upstream.
- A contingência sem INLABS continua funcionando (testes de `tests/local/test_pdf_search.py` e smoke fora do pytest).
- O instalador gerado a partir de `main` passa o checklist do Sprint 6.
- Um ensaio de sync com o upstream passa.
- Nenhuma branch, worktree ou stash obsoleta.

**Registro:**
- **O que foi feito:**
  - Remoção definitiva de Docker, Airflow e Kubernetes: `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `.dockerignore`, `Makefile`, `Makefile.backup`, `generate-Makefile.sh`, `instalar.bat`, `rodou_dashboard/Dockerfile`, `docs/Dockerfile`, `docs/docker-compose.yml`, `helm/`, `src/dou_dag_generator.py`, `dag_load_inlabs/`, `.github/workflows/ci-tests.yml`, `.github/workflows/docker_build_and_publish.yml` e os testes exclusivos do Airflow (`tests/dag_generator_test.py`, `tests/dag_generator_invalid_yaml_test.py`, `tests/test_dag_loading.py`, `tests/test_e2e_dag_execution.py`).
  - `dag_load_inlabs/sql/init-db.sql` movido para `rodou_dashboard/app/runtime/sql/init-db.sql`, com atualização de `rodou_dashboard/app/runtime/pg_portable.py::_load_init_sql_statements` e `windows/build.ps1`.
  - Mantidos `src/utils/open_search/` (importado por `src/hooks/inlabs_hook.py`), `compat/airflow_shim/`, `compat/bootstrap.py`, alias `ro_dou_src` em `runtime/runner.py` e contingência INLABS (`PDF integral → API do DOU`, `inlabs_fallback`).
  - Removidos `rodou_dashboard/app/services/airflow_service.py`, `AirflowExecutor`, `get_executor_mode()`, `REGISTRALE_EXECUTOR` e todos os ramos Airflow em `executor.py`, `paths.py`, `server.py`, `inlabs_service.py`, `dag_config_service.py`, `__init__.py`, `routes/admin.py`, `routes/dags.py`, `templates/index.html` e `windows/launcher.pyw`.
  - Atualizados `tests/conftest.py`, `tests/parsers_test.py`, `rodou_dashboard/tests/conftest.py` (isolamento de `REGISTRALE_DATA_DIR`), `rodou_dashboard/tests/test_dashboard.py` e `tests/local/*.py` (remoção de `REGISTRALE_EXECUTOR` e mocks do Airflow).
  - Atualizados `plano/UPSTREAM.md` e `tools/sync_upstream.py` (`REMOVED_PATHS` com os 20 caminhos removidos).
  - Limpeza de git e Podman (autorizada pelo usuário): removidos worktree `Registrale-dou-sync`, branch `upstream-sync`, stash `backup-pre-merge`, 13 containers antigos (`sync-*` e modo Docker; mantido `windows-registrale`) e 11 imagens antigas de Airflow/projeto.
  - Reescritos `README.md` e `AGENTS.md` para o estado pós-migração, atualizado `.gitignore` (`dist/`, `vendor/`), e atualizados `MANUAL.md` e `rodou_dashboard/docs/05_guia_operacional_e_deploy.md`.
- **Decisões tomadas:**
  - Mantido o label de importação `Arquivo database.db (Docker)` em `templates/index.html` e `import_docker_database()` em `runtime/migrator.py` para permitir migração de bancos legados no onboarding.
  - Mantidas as variáveis legadas `AIRFLOW__SMTP__SMTP_*` apenas como fallback de leitura de `.env` em `email_service.py` e gravação compatível em `admin.py`/`dags.py`.
  - `src/` não recebeu novos patches locais (apenas remoção de `src/dou_dag_generator.py`, já registrada em `plano/UPSTREAM.md`).
- **Arquivos criados/alterados:**
  - Criado: `rodou_dashboard/app/runtime/sql/init-db.sql`.
  - Removidos: artefatos Docker/Airflow/Helm/CI e testes `@pytest.mark.airflow` listados acima + `airflow_service.py`.
  - Alterados: `README.md`, `AGENTS.md`, `MANUAL.md`, `.gitignore`, `plano/UPSTREAM.md`, `plano/PLANO.md`, `tools/sync_upstream.py`, `.github/workflows/windows-build.yml`, `windows/build.ps1`, `windows/launcher.pyw`, `rodou_dashboard/docs/05_guia_operacional_e_deploy.md`, `rodou_dashboard/templates/index.html`, `rodou_dashboard/app/__init__.py`, `rodou_dashboard/app/routes/{admin,dags}.py`, `rodou_dashboard/app/runtime/{executor,paths,pg_portable,server}.py`, `rodou_dashboard/app/services/{dag_config_service,inlabs_service}.py`, `tests/{conftest,parsers_test}.py`, `tests/local/*.py`, `rodou_dashboard/tests/{conftest,test_dashboard}.py`.
- **Validações:**
  - `uv run pytest tests/local/test_pdf_search.py -m "not live" -q` → `18 passed, 1 deselected`.
  - `uv run pytest -m "not live" -q` → `613 passed, 3 deselected`.
  - Smoke fora do pytest (`_build_default_searchers()` + `uv run registrale --port 5099` + `GET /login`) → `['DOESP', 'DOU', 'INLABS', 'INLABS_FALLBACK', 'QD']` e `HTTP 200`.
  - `grep -rni "docker\|airflow\|helm\|make run"` → retorna apenas o shim (`compat/`), `ro_dou_src`, `src/` do upstream, `CHANGELOG.md`, referências de importação/migração legada e `plano/UPSTREAM.md`.
- **Pendências:**
  - **Build e checklist do instalador Windows (Sprint 6) a partir de `main`:** não executado nesta sessão porque o container `windows-registrale` expõe apenas RDP (`3389`) e noVNC (`8006`), sem shell remoto (SSH/WinRM) disponível; validar via workflow `.github/workflows/windows-build.yml` ou interativamente na VM Windows (fazendo backup de `%LOCALAPPDATA%\Registrale` antes).
  - **Revisão independente:** executar `plano/prompts/revisao.md` para o Sprint 8.
---

## Sprint 9: Pasta dos PDFs no onboarding, janela própria e ícone

**Pré-condição:** Sprint 8 revisado (o app já é só modo local). Pedido do usuário em 24/11/2026.

**Objetivo:** o analista escolhe onde e como os PDFs do DOU são guardados já no primeiro uso, o painel abre numa janela própria (fora do navegador) e o `.exe`, o atalho e a bandeja usam o mesmo ícone do site.

**Situação atual (24/11/2026)**
- A pasta já é configurável em Configurações (`global_settings.pdf_archive.folder`, padrão `Documentos\Registrale\DOU`), mas não aparece no primeiro uso. O primeiro uso hoje é só a importação (`/api/admin/first_run_status` e `/api/admin/first_run_import`, `templates/index.html` perto da linha 3840).
- A organização das pastas é fixa em `<pasta>/<AAAA>/<MM>/`. Ela está repetida em `pdf_archiver.build_pdf_target_path` (linha ~134), `resolve_pdf_for_mention` e `pdf_search.ensure_day_pdfs` (`day_dir`, linha ~131).
- O ícone do site é `rodou_dashboard/static/icon.svg` (mais `icon-192.png` e `icon-512.png`). O instalador, os atalhos e a bandeja usam `windows/registrale.ico`, que é outro desenho.
- O launcher abre o navegador padrão em `http://localhost:5000`.

**Tarefas**
1. **Organização das pastas configurável:**
   - novo campo `pdf_archive.layout` com os valores `ano_mes` (padrão, igual a hoje: `AAAA/MM/`), `ano` (`AAAA/`) e `nenhum` (tudo direto na pasta);
   - um único ponto de cálculo do caminho (`build_pdf_target_path`), usado pelo arquivador, pela busca de contingência (`ensure_day_pdfs` deixa de montar `day_dir` sozinho) e pela localização do PDF da menção;
   - o nome do arquivo continua `DOU_<AAAA-MM-DD>_<Seção>.pdf`, então o layout `nenhum` não gera colisão;
   - mudar o layout ou a pasta **não move nem apaga** arquivos já salvos: a localização procura primeiro no layout atual e depois nos outros dois, e o painel oferece "Reorganizar PDFs existentes", que só move com confirmação, nunca sobrescreve e mostra quantos arquivos foram movidos ou ignorados;
   - validar a pasta escolhida: caminho absoluto, gravável, sem path traversal e sem ser a pasta do programa; no Windows, aceitar unidades e caminhos de rede (`\\servidor\pasta`), mas avisar se não estiver acessível;
   - o cache interno (`<dados>/pdf_cache`, usado quando o arquivamento está desligado) continua fora dessa escolha.
2. **Onboarding (primeiro uso):** um passo "Onde guardar os PDFs do DOU" com:
   - a pasta (com o padrão preenchido e um botão Procurar);
   - a organização (`Por ano e mês`, `Só por ano` ou `Tudo na mesma pasta`), com uma prévia do caminho de um arquivo de exemplo;
   - as seções a arquivar;
   - grava em `pdf_archive` e marca o passo como feito; aparece também em instalação que já tinha dados, uma única vez, para quem nunca escolheu;
   - o mesmo controle fica em Configurações. O botão Procurar usa o diálogo nativo quando o painel está na janela própria (tarefa 3); no navegador, só o campo de texto.
3. **Janela própria (fora do navegador):**
   - `pywebview` (WebView2 do Windows, que já vem no Windows 10/11 atualizado), aberto pelo `launcher.pyw` apontando para o servidor local; **não** usar Electron (decisão de 24/11/2026: ~150 MB a mais e outra tecnologia para manter);
   - fechar a janela só a esconde: o servidor e o agendador continuam na bandeja; "Abrir painel" na bandeja reabre a janela; "Sair" encerra tudo;
   - se o WebView2 não existir ou falhar, abrir no navegador padrão como hoje e registrar o motivo no log;
   - downloads (relatórios, PDFs) e links externos (DOU, `pesquisa.in.gov.br`) abrem no app padrão do Windows ou no navegador, sem quebrar a sessão;
   - login, sessão, CSRF e o service worker (`static/sw.js`) continuam funcionando dentro da janela;
   - `pywebview` vai no grupo `windows` do `pyproject.toml`, como `pystray`.
4. **Ícone:**
   - gerar `windows/registrale.ico` a partir de `static/icon.svg` (tamanhos 16, 24, 32, 48, 64, 128 e 256) com um script versionado (ex.: `windows/make_icon.py`), para que um novo ícone do site se propague com um comando;
   - usar o mesmo ícone no instalador (`SetupIconFile`), no desinstalador, nos atalhos, na bandeja (`pystray`) e na janela do `pywebview`;
   - o `build.ps1` falha se o `.ico` estiver mais antigo que o `icon.svg`.
5. Atualizar o `README.md`, o manual do painel e o `AGENTS.md` (pasta e organização dos PDFs, janela própria).

**Fora de escopo:** mudar a fonte ou a lógica de busca da contingência, o nome dos arquivos de PDF e a regra de CNPJ.

**Critério de aceite**
- Testes offline para os três layouts: caminho gerado, localização do PDF da menção, busca de contingência achando os PDFs no layout escolhido, troca de layout sem perder a localização dos arquivos antigos, e reorganização sem sobrescrever.
- Validação da pasta rejeita caminho relativo, sem permissão de escrita e a pasta do programa.
- Instalação limpa na VM Windows: o onboarding pede a pasta e a organização, e o primeiro arquivamento grava no lugar escolhido.
- Atualização por cima de uma instalação que já tinha PDFs em `AAAA/MM/`: nada é movido sem confirmação e as menções antigas continuam abrindo o PDF.
- O painel abre numa janela própria; fechar e reabrir pela bandeja funciona; sem WebView2 cai para o navegador.
- O `.exe`, os atalhos, a bandeja e a janela mostram o ícone do site.
- Novembro/2026 continua com 26 menções de 16 empresas pela contingência PDF em cada layout (pode ser com os PDFs já baixados).

**Registro:**
- **O que foi feito:**
  - Remoção definitiva de Docker, Airflow e Kubernetes: `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `.dockerignore`, `Makefile`, `Makefile.backup`, `generate-Makefile.sh`, `instalar.bat`, `rodou_dashboard/Dockerfile`, `docs/Dockerfile`, `docs/docker-compose.yml`, `helm/`, `src/dou_dag_generator.py`, `dag_load_inlabs/`, `.github/workflows/ci-tests.yml`, `.github/workflows/docker_build_and_publish.yml` e os testes exclusivos do Airflow (`tests/dag_generator_test.py`, `tests/dag_generator_invalid_yaml_test.py`, `tests/test_dag_loading.py`, `tests/test_e2e_dag_execution.py`).
  - `dag_load_inlabs/sql/init-db.sql` movido para `rodou_dashboard/app/runtime/sql/init-db.sql`, com atualização de `rodou_dashboard/app/runtime/pg_portable.py::_load_init_sql_statements` e `windows/build.ps1`.
  - Mantidos `src/utils/open_search/` (importado por `src/hooks/inlabs_hook.py`), `compat/airflow_shim/`, `compat/bootstrap.py`, alias `ro_dou_src` em `runtime/runner.py` e contingência INLABS (`PDF integral → API do DOU`, `inlabs_fallback`).
  - Removidos `rodou_dashboard/app/services/airflow_service.py`, `AirflowExecutor`, `get_executor_mode()`, `REGISTRALE_EXECUTOR` e todos os ramos Airflow em `executor.py`, `paths.py`, `server.py`, `inlabs_service.py`, `dag_config_service.py`, `__init__.py`, `routes/admin.py`, `routes/dags.py`, `templates/index.html` e `windows/launcher.pyw`.
  - Atualizados `tests/conftest.py`, `tests/parsers_test.py`, `rodou_dashboard/tests/conftest.py` (isolamento de `REGISTRALE_DATA_DIR`), `rodou_dashboard/tests/test_dashboard.py` e `tests/local/*.py` (remoção de `REGISTRALE_EXECUTOR` e mocks do Airflow).
  - Atualizados `plano/UPSTREAM.md` e `tools/sync_upstream.py` (`REMOVED_PATHS` com os 20 caminhos removidos).
  - Limpeza de git e Podman (autorizada pelo usuário): removidos worktree `Registrale-dou-sync`, branch `upstream-sync`, stash `backup-pre-merge`, 13 containers antigos (`sync-*` e modo Docker; mantido `windows-registrale`) e 11 imagens antigas de Airflow/projeto.
  - Reescritos `README.md` e `AGENTS.md` para o estado pós-migração, atualizado `.gitignore` (`dist/`, `vendor/`), e atualizados `MANUAL.md` e `rodou_dashboard/docs/05_guia_operacional_e_deploy.md`.
- **Decisões tomadas:**
  - Mantido o label de importação `Arquivo database.db (Docker)` em `templates/index.html` e `import_docker_database()` em `runtime/migrator.py` para permitir migração de bancos legados no onboarding.
  - Mantidas as variáveis legadas `AIRFLOW__SMTP__SMTP_*` apenas como fallback de leitura de `.env` em `email_service.py` e gravação compatível em `admin.py`/`dags.py`.
  - `src/` não recebeu novos patches locais (apenas remoção de `src/dou_dag_generator.py`, já registrada em `plano/UPSTREAM.md`).
- **Arquivos criados/alterados:**
  - Criado: `rodou_dashboard/app/runtime/sql/init-db.sql`.
  - Removidos: artefatos Docker/Airflow/Helm/CI e testes `@pytest.mark.airflow` listados acima + `airflow_service.py`.
  - Alterados: `README.md`, `AGENTS.md`, `MANUAL.md`, `.gitignore`, `plano/UPSTREAM.md`, `plano/PLANO.md`, `tools/sync_upstream.py`, `.github/workflows/windows-build.yml`, `windows/build.ps1`, `windows/launcher.pyw`, `rodou_dashboard/docs/05_guia_operacional_e_deploy.md`, `rodou_dashboard/templates/index.html`, `rodou_dashboard/app/__init__.py`, `rodou_dashboard/app/routes/{admin,dags}.py`, `rodou_dashboard/app/runtime/{executor,paths,pg_portable,server}.py`, `rodou_dashboard/app/services/{dag_config_service,inlabs_service}.py`, `tests/{conftest,parsers_test}.py`, `tests/local/*.py`, `rodou_dashboard/tests/{conftest,test_dashboard}.py`.
- **Validações:**
  - `uv run pytest tests/local/test_pdf_search.py -m "not live" -q` → `18 passed, 1 deselected`.
  - `uv run pytest -m "not live" -q` → `613 passed, 3 deselected`.
  - Smoke fora do pytest (`_build_default_searchers()` + `uv run registrale --port 5099` + `GET /login`) → `['DOESP', 'DOU', 'INLABS', 'INLABS_FALLBACK', 'QD']` e `HTTP 200`.
  - `grep -rni "docker\|airflow\|helm\|make run"` → retorna apenas o shim (`compat/`), `ro_dou_src`, `src/` do upstream, `CHANGELOG.md`, referências de importação/migração legada e `plano/UPSTREAM.md`.
- **Pendências:**
  - **Build e checklist do instalador Windows (Sprint 6) a partir de `main`:** não executado nesta sessão porque o container `windows-registrale` expõe apenas RDP (`3389`) e noVNC (`8006`), sem shell remoto (SSH/WinRM) disponível; validar via workflow `.github/workflows/windows-build.yml` ou interativamente na VM Windows (fazendo backup de `%LOCALAPPDATA%\Registrale` antes).
  - **Revisão independente:** executar `plano/prompts/revisao.md` para o Sprint 8.
---

## Backlog

- **Exportar a página com a menção destacada (standby):** gerar, para cada menção, o PDF só da página do DOU onde a empresa aparece, com o CNPJ destacado, salvo junto do PDF do dia. Depende do Sprint 5 (fonte do PDF e localização da página: `numberpage` no INLABS e `pdfpage` no XML).
- Busca opcional por razão social (citações sem CNPJ, como despachos do CADE), marcada como "por nome" e sujeita a revisão, por causa dos falsos positivos.
- Não enviar segredos ao navegador na página de configurações (hoje o HTML do usuário master contém senhas e a chave do Google), e não apagar tokens salvos quando o campo for enviado vazio.
- Tempo limite menor com mais tentativas na API do DOU (10 s × 5 em vez de 35 s × 3) para dias de portal instável.
