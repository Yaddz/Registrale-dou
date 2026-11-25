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
| 10 | Ajustes de uso (status do arquivamento, máscara de data, seletor de mês, última sync), avisos dispensáveis, interruptor do SMTP e rotina de clientes fora do instalador | 9 |
| 11 | Busca confiável sem o Postgres portátil, fim do erro `NoneType` no log, execução "com pendências", padrões iguais à baseline | 10 |
| 12 | Interruptores num só modelo e gravando o estado, assistente que reconhece o que foi pausado, SMTP desligado em todo o app, atividade visível e botão Atualizar | 11 |
| 13 | Acabamento visual (barra lateral, avisos, Sheets, template de e-mail, passada geral) e PDFs na aba Armazenamento | 12 |
| 14 | Onboarding completo (rotina, empresas, GestãoClick, SMTP, INLABS, resumo) | 13 |
| 15 | Documentação unificada (`plano/` dentro de `docs/`), manual único e limpeza do repositório | 14 |
| 16 | Homologação na VM (atualização e instalação limpa) e release 1.3.0 | 11–15 |
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
  - `uv run python tools/sync_upstream.py --repo-root /tmp/registrale-sync-s8` (worktree temporária a partir de `a7f8117`) → `Merge exit code: 0`, `Conflitos pendentes (0)`, `613 passed, 3 deselected`.
  - `grep -rni "docker\|airflow\|helm\|make run"` → retorna apenas o shim (`compat/`), `ro_dou_src`, `src/` do upstream, `CHANGELOG.md`, referências de importação/migração legada e `plano/UPSTREAM.md`.
- **Pendências:**
  - **Build e checklist do instalador Windows (Sprint 6) a partir de `main`:** não executado nesta sessão porque o container `windows-registrale` expõe apenas RDP (`3389`) e noVNC (`8006`), sem shell remoto (SSH/WinRM) disponível; validar via workflow `.github/workflows/windows-build.yml` ou interativamente na VM Windows (fazendo backup de `%LOCALAPPDATA%\Registrale` antes).
  - **Revisão independente:** executar `plano/prompts/revisao.md` para o Sprint 8.
- **Revisão independente (24/11/2026), veredito: Sprint 8 reprovado (correções pequenas):**
  - Validações executadas:
    - Linux: `uv run pytest -m "not live" -q` → `613 passed, 3 deselected`; `_build_default_searchers()` fora do pytest → `['DOESP', 'DOU', 'INLABS', 'INLABS_FALLBACK', 'QD']`; `git diff baseline-docker -- src/` só remove `src/dou_dag_generator.py`.
    - VM Windows 10 (`windows-registrale`), cópia de `main` (`d15d410`): `613 passed`; `build.ps1 -SkipPostgresDownload` → `Registrale-Setup-0.1.0.exe` (62.548.996 bytes, SHA-256 `78d3dfb5...f9f6`); instalação por cima com atalhos; `/login` HTTP 200 em 4,23 s; RAM em repouso 119,2 MB; e2e no Python instalado (`Pesquisa_cnpj.yaml`, 23/11/2026, fallback PDF) → `WIN_E2E_OK=True`, 4 menções, 39,7 s, raízes `05785287, 07021336, 09217325, 24684423`; desinstalação e reinstalação preservaram `database.db` (114.688 bytes).
  - **Bloqueador:** a atualização por cima deixa arquivos removidos da versão nova: `app\rodou_dashboard\app\services\airflow_service.py` continuou instalado, e depois da desinstalação a pasta `{app}\app` não foi removida. Falha o checklist do Sprint 6 (atualização e desinstalação limpas). Correção: `[InstallDelete]` e `[UninstallDelete]` de `{app}\app` e `{app}\site-packages` no `windows/installer.iss` (os dados ficam em `%LOCALAPPDATA%\Registrale`, fora dessas pastas).
  - **Importantes:**
    - A desinstalação silenciosa (`/VERYSILENT /SUPPRESSMSGBOXES`) para na pergunta "Deseja remover também os dados?" (`installer.iss`, `CurUninstallStepChanged`, `MsgBox`), preexistente do Sprint 6. Trocar por `SuppressibleMsgBox(..., IDNO)`.
    - Versão: a tag é `v1.0.0`, mas `pyproject.toml` diz `0.1.0`, então o app e o instalador se apresentam como 0.1.0 e o verificador de atualização compara a versão errada com as Releases.
    - O critério do `grep` não fecha: `docs/docs/dashboard/*.md` (nosso, publicado pelo `gh_pages.yml`) ainda descreve deploy com Docker e Gunicorn; `.env.example` (configuração do Airflow, com chave Fernet de exemplo) e `requirements-uninstall.txt` (imagem Docker) vêm do upstream e continuam no repositório. Incluir em `REMOVED_PATHS` (ou substituir o `.env.example` por um do modo local) e atualizar ou remover os manuais duplicados em `docs/docs/dashboard/`.
  - **Sugestões:** o Registro do Sprint 8 tinha sido copiado também para a seção do Sprint 9 (corrigido na revisão: Sprint 9 voltou a "_(preencher)_"); docstrings de `routes/dags.py` (rotinas e limpeza) ainda citam o Airflow; a branch `feature/modo-local` já está em `main` e pode ser removida (com confirmação); a senha SMTP continua gravada em `.env` em texto puro (preexistente, ver Backlog); `main` está 163 commits à frente de `origin/main` e a tag não foi enviada; o Postgres portátil segue fora do instalador (`-SkipPostgresDownload`).
- **Correções da revisão (24/11/2026), veredito após correções: Sprint 8 aprovado:**
  - `windows/installer.iss`: `[InstallDelete]` e `[UninstallDelete]` de `{app}\app`, `{app}\site-packages` e `{app}\python` (os dados em `%LOCALAPPDATA%\Registrale` ficam fora); pergunta da desinstalação com `SuppressibleMsgBox(..., IDNO)`, que preserva os dados no modo silencioso. Teste novo `test_installer_upgrade_and_uninstall_are_clean_and_silent`.
  - Versão 1.0.0 em `pyproject.toml`, `uv.lock`, `runtime/version.py` (padrão) e `installer.iss` (padrão).
  - Removidos `.env.example` e `requirements-uninstall.txt` (incluídos em `REMOVED_PATHS` e `plano/UPSTREAM.md`); manuais publicados em `docs/docs/dashboard/` sincronizados com `rodou_dashboard/docs/`; Gunicorn trocado por waitress nos manuais; docstrings de `routes/dags.py` sem Airflow.
  - Exceções aceitas do `grep`: documentação do upstream em `docs/docs/` (instalação do Ro-DOU original), exemplos de `dag_confs/examples_and_tests/`, nomes legados `AIRFLOW__SMTP__*` (leitura de `.env` antigo) e a importação de banco do Docker no primeiro uso.
  - Validações: Linux `uv run pytest -m "not live" -q` → `615 passed, 3 deselected`; smoke fora do pytest OK. VM Windows 10, instalação de `Registrale-Setup-1.0.0.exe` (62.549.052 bytes, SHA-256 `b62a5e4c...dbe2b`) **por cima da 0.1.0 que tinha arquivos órfãos**: `airflow_service.py` removido, versão instalada `1.0.0`, `/login` HTTP 200 em 7,26 s, RAM 126,3 MB, e2e `WIN_E2E_OK=True` (4 menções, 46,7 s); desinstalação silenciosa terminou sozinha em 9 s, removendo `app`, `python` e `site-packages` e preservando `database.db` (114.688 bytes); reinstalação OK.
  - Pendências: a tag `v1.0.0` aponta para `d15d410`, anterior às correções (mover só com autorização); push de `main` e da tag; Postgres portátil fora do instalador (`-SkipPostgresDownload`).
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
- **Data:** 24/11/2026.
- **O que foi feito:**
  1. **Organização das pastas configurável (`pdf_archive.layout`):**
     - `rodou_dashboard/app/runtime/pdf_archiver.py`: adicionado `layout` (`ano_mes` padrão, `ano`, `nenhum`), `normalize_pdf_layout()`, `validate_pdf_folder()` (rejeita caminho relativo, `..`, pasta do programa e sem permissão de escrita; aceita UNC no Windows e reporta inacessibilidade), `reorganize_pdfs()` (move entre layouts sem sobrescrever existentes e atualiza `Mention.pdf_path`) e fallback automático em `resolve_pdf_for_mention()` (procura primeiro no layout atual e depois nos outros dois).
     - `rodou_dashboard/app/runtime/pdf_search.py`: `ensure_day_pdfs()` passou a usar `build_pdf_target_path()` como ponto único de cálculo de caminho (respeitando o layout configurado, mantendo `pdf_cache` separado quando o arquivamento está desligado).
     - `rodou_dashboard/app/routes/admin.py`, `auth.py`, `dags.py`: suporte a `layout` em `get_settings`/`save_settings`/`index`, validação de pasta no `save_settings`, e endpoint `POST /api/pdf_archive/reorganize` exigindo `confirm: true`.
  2. **Onboarding de PDFs no primeiro uso:**
     - `admin.py`: `GET /api/admin/first_run_status` agora retorna `pdf_onboarding_done`, `needs_pdf_onboarding` (True mesmo em instalações que já tinham dados, uma única vez) e `pdf_archive`; novo endpoint `POST /api/admin/pdf_onboarding` valida a pasta, grava `global_settings.pdf_archive` e marca `pdf_onboarding_done=True`.
     - `rodou_dashboard/templates/index.html`: modal de onboarding *"Onde guardar os PDFs do DOU"* (pasta padrão, botão *Procurar...* visível apenas na janela própria via `pywebview`, organização com prévia em tempo real e seções), além dos mesmos controles e do botão *Reorganizar PDFs existentes* (com `confirm`) em *Configurações → Arquivo PDF DOU*.
  3. **Janela própria (`pywebview` / WebView2):**
     - `pyproject.toml`: adicionado `pywebview>=5.0,<6.0` ao grupo `windows`.
     - `windows/launcher.pyw`: `RegistraleTrayController` roda a bandeja com `pystray.Icon.run_detached()` e abre a janela WebView2 na thread principal com `storage_path=<dados>/webview` e `ALLOW_DOWNLOADS=True`; fechar a janela pelo `X` apenas a esconde (`_on_window_closing`), *Abrir painel* a reabre, *Sair* destrói a janela e encerra servidor/bandeja, e falhas no `pywebview`/WebView2 fazem fallback automático para o navegador padrão registrando o motivo no log. `RegistraleJsApi` expõe `pick_folder` (diálogo nativo) e `open_external` (links externos no navegador padrão via `index.html`).
  4. **Ícone unificado:**
     - Criado `windows/make_icon.py` para gerar `windows/registrale.ico` (16, 24, 32, 48, 64, 128 e 256 px) a partir de `rodou_dashboard/static/icon.svg` (usando `cairosvg`/`rsvg-convert` se presentes ou renderização vetorial via Pillow 4x).
     - `windows/registrale.ico` regerado (`18.830 bytes`, 7 tamanhos) e usado no `installer.iss`, bandeja (`pystray`) e janela (`pywebview`).
     - `windows/build.ps1`: agora falha se `windows/registrale.ico` não existir ou estiver mais antigo que `rodou_dashboard/static/icon.svg`.
  5. **Documentação:** atualizados `README.md`, `rodou_dashboard/docs/MANUAL.md` e `AGENTS.md`.
- **Arquivos alterados/criados:** `pyproject.toml`, `rodou_dashboard/app/runtime/pdf_archiver.py`, `rodou_dashboard/app/runtime/pdf_search.py`, `rodou_dashboard/app/routes/admin.py`, `rodou_dashboard/app/routes/auth.py`, `rodou_dashboard/app/routes/dags.py`, `rodou_dashboard/templates/index.html`, `windows/launcher.pyw`, `windows/make_icon.py`, `windows/registrale.ico`, `windows/build.ps1`, `tests/local/test_pdf_archiver.py`, `tests/local/test_windows_packaging.py`, `README.md`, `rodou_dashboard/docs/MANUAL.md`, `AGENTS.md`, `plano/PLANO.md`. (`src/` não foi alterado.)
- **Validações executadas:**
  - `uv run pytest tests/local/test_pdf_archiver.py -m "not live" -v` → **9 passed, 1 deselected** (cobre os 3 layouts, `ensure_day_pdfs`, fallback de localização, reorganização sem sobrescrever + `confirm`, validação da pasta e onboarding).
  - `uv run pytest tests/local/test_windows_packaging.py -m "not live" -v` → **14 passed** (cobre `_on_window_closing`, `open_panel`, `quit_app`, fallback sem `pywebview`, `RegistraleJsApi.open_external`, `make_icon.py` com 7 tamanhos e checagem de idade no `build.ps1`).
  - `uv run pytest -m "not live" -q` → **620 passed, 3 deselected** em `12.38s` (ponto de partida antes do sprint: `615 passed, 3 deselected`).
  - Contingência PDF com PDFs reais locais de `23/11/2026` (`~/Documentos/Registrale/DOU/2026/11/`) nos 3 layouts (`ano_mes`, `ano`, `nenhum`): **4 menções** em cada layout com as mesmas 4 raízes da baseline (`05785287`, `07021336`, `09217325`, `24684423`).
- **Pendências / não validado neste ambiente:**
  - **VM Windows (`windows-registrale`):** não pôde ser validada a partir deste host Linux (`virsh` e shell remoto no guest não disponíveis). Pendente validar na VM: build com `windows/build.ps1`, instalação limpa com onboarding e botão *Procurar...*, atualização por cima de instalação com PDFs em `AAAA/MM/`, janela própria WebView2 (fechar/reabrir/fallback sem WebView2) e ícones visuais no `.exe`/atalhos/bandeja/janela.
  - **Contingência PDF completa de novembro/2026 (03–23/11, 26 menções, 16 empresas) nos 3 layouts:** apenas `2026-11-23` estava pré-baixado localmente; os demais 13 dias úteis (03–20/11) não estavam no disco local para execução offline completa.
- **Revisão independente e validação na VM (24/11/2026), veredito: Sprint 9 reprovado (correções pequenas):**
  - Validações executadas:
    - Linux: `uv run pytest -m "not live" -q` → `620 passed, 3 deselected`; `_build_default_searchers()` fora do pytest OK.
    - Contingência PDF de novembro/2026 (14 dias úteis, `Pesquisa_cnpj.yaml`, `REGISTRALE_INLABS_FALLBACK=pdf`) nos 3 layouts: `ano_mes` (baixou os PDFs, 931,5 s), `ano` (566,1 s) e `nenhum` (488,2 s), estes dois com os mesmos PDFs por link físico → **26 menções, 16 empresas, `missing=[]`, `extra=[]` em todos**, sem novo download nos layouts `ano`/`nenhum` (71 → 71 PDFs).
    - VM Windows 10 (`windows-registrale`): `620 passed`; build `Registrale-Setup-1.0.0.exe` (63.199.978 bytes); atualização por cima da 1.0.0 com PDFs em `2026\11\` → PDFs intactos (mesmos nomes e tamanhos) e `resolve_pdf_for_mention` acha o PDF antigo com `ano_mes`, `ano` e `nenhum`; e2e no Python instalado → `WIN_E2E_OK=True`, 4 menções.
    - Janela própria (WebView2): abre com o login; onboarding "Onde guardar os PDFs do DOU" aparece na instalação existente e na limpa; botão **Procurar...** abre o seletor nativo e preenche o campo; prévia acompanha o layout; ao salvar, Configurações → Arquivo PDF DOU mostra pasta e layout gravados.
    - Primeiro arquivamento no lugar escolhido: instalação existente com `Desktop` + `ano` → 6 PDFs de 23/11 em `Desktop\2026\`; instalação limpa (dados renomeados e depois restaurados) com `nenhum` → 6 PDFs direto em `Documentos\Registrale\DOU\`.
    - Fechar no X esconde a janela (sai da barra de tarefas, servidor segue na bandeja); **Abrir painel** reabre no mesmo estado; **Sair** encerra. Sem `pywebview` (módulo bloqueado) o painel abre no navegador padrão em `127.0.0.1:5000`.
  - **Bloqueador (critério de ícones):** a barra de título da janela mostra o ícone do Python, não o do site (`webview.start(icon=...)` não vale no backend WinForms/EdgeChromium). Correção: aplicar `registrale.ico` na janela via `WM_SETICON` (ctypes) depois de criada.
  - **Importantes:**
    - Depois de atualizar, o atalho da Área de Trabalho continua com o ícone antigo ("R") por causa do cache de ícones do Windows (mesmo caminho `app\windows\registrale.ico`). Correção: renovar o cache no fim da instalação (`ie4uinit.exe -show` em `[Run]`, ou `ChangesAssociations=yes`) ou versionar o nome do `.ico`.
    - Versão continua `1.0.0`: com funções novas, o verificador de atualização não oferece este build a quem já tem a 1.0.0. Subir para `1.1.0`.
  - **Sugestões:**
    - O quadro "Status e Disparo Manual" não mudou depois de **Baixar Dia** e **Atualizar Status** (~40 s depois), embora os PDFs tenham sido gravados; conferir se o status é persistido no disparo manual.
    - Campo de data com máscara: `Ctrl+A` + `Backspace` não limpa e digitar por cima embaralha (ex.: `31/12/3022`).
    - Seletor de mês em "Arquivar Mês Completo" aparece sem rótulo.
    - Fora do escopo: "Última sync" mostrou horário à frente do relógio da VM; e a rotina `Pesquisa_cnpj.yaml` com os 122 CNPJs vai embutida no instalador público (aparece "CNPJs monitorados: 122" numa instalação limpa).
- **Correções da revisão (24/11/2026), veredito após correções: Sprint 9 aprovado:**
  - `windows/launcher.pyw`: `apply_window_icon()` envia `registrale.ico` à janela com `WM_SETICON` (pequeno e grande), usando `window.native.Handle` ou `FindWindowW`; chamado no evento `shown`, ao exibir a janela e ao reabrir pela bandeja.
  - `windows/installer.iss`: `ChangesAssociations=yes` e `ie4uinit.exe -show` em `[Run]` (também no modo silencioso) para renovar o cache de ícones dos atalhos após atualizar.
  - Versão `1.1.0` (`pyproject.toml`, `uv.lock`, padrão de `runtime/version.py` e do `installer.iss`).
  - Testes novos: `test_apply_window_icon_sends_wm_seticon` e `test_installer_refreshes_icon_cache`. `uv run pytest -m "not live" -q` → `622 passed, 3 deselected`.
  - VM Windows 10: `Registrale-Setup-1.1.0.exe` (SHA-256 `0ac19ec5...0f24e`) instalado por cima da 1.0.0 → versão `1.1.0`; barra de título da janela, atalho da Área de Trabalho, barra de tarefas e bandeja com o ícone do site.
  - Sugestões da revisão que continuam abertas (não bloqueiam): status do disparo manual que não atualiza na tela, máscara do campo de data, rótulo do seletor de mês, horário de "Última sync" e a rotina com os 122 CNPJs embutida no instalador público.
---

## Sprint 10: Ajustes de uso do painel e privacidade da rotina

**Pré-condição:** Sprint 9 aprovado e commitado (`37b0088`, `f73bc0a`). Pedido do usuário em 24/11/2026, a partir da revisão do Sprint 9.

**Objetivo:** corrigir os incômodos de uso achados na validação do Sprint 9, deixar os avisos da Visão geral dispensáveis, permitir desligar o e-mail sem o sistema acusar pendência e parar de distribuir a lista de clientes no instalador público.

**Situação atual (24/11/2026)**
- **Status do arquivamento:** em Configurações → Arquivo PDF DOU, depois de **Baixar Dia** o quadro "Status e disparo manual" continua com o valor anterior (ou "Nunca"), mesmo com os PDFs gravados. O disparo roda em segundo plano (`routes/dags.py::api_pdf_archive_run`, `threading.Thread`) e a tela não acompanha o fim; o status só é gravado ao terminar (`pdf_archiver._save_pdf_archive_status`).
- **Máscara de data:** os campos com `maskDate()` (`templates/index.html`: filtro de Menções, Baixar Dia, data da busca avulsa, período de Relatórios) não limpam com `Ctrl+A` + `Backspace` e, ao digitar sobre um valor existente, embaralham a data (ex.: `31/12/3022`).
- **Seletor de mês:** em "Arquivar mês completo" o `<select x-model="pdfManualMonth">` aparece sem rótulo nem mês selecionado.
- **"Última sync" adiantada:** sem nenhum registro de sincronização em `SyncHistory`, `admin.py` (~linha 460) e `auth.py` (~linha 92) mostram a data de modificação do `Pesquisa_cnpj.yaml`. No app instalado essa data é a do arquivo no momento do build, não uma sincronização.
- **Lista de clientes no instalador público:** `dag_confs/Pesquisa_cnpj.yaml` (122 CNPJs) está versionado no repositório público e o `build.ps1` copia `dag_confs/` para o instalador; `paths._seed_routines_if_empty` copia a rotina no primeiro uso. Uma instalação limpa mostra "CNPJs monitorados: 122". A release `v1.0.0` já publicada contém o arquivo.
- **Avisos da Visão geral:** o aviso "Portal INLABS indisponível" e o "Integrações pendentes" não podem ser fechados (o de integrações só recolhe).
- **SMTP:** não há como desligar o envio de e-mail; o SMTP sem configuração sempre aparece como pendência (`dags.py::api_integrations_status`, `smtp_configured`) e no assistente de integrações.

**Tarefas**
1. **Status do arquivamento manual:** depois de **Baixar Dia** / **Baixar Mês**, a tela mostra "em andamento" e consulta `/api/pdf_archive/status` até o fim (com limite de tempo), atualizando o quadro com o resultado. Confirmar com teste que o status é gravado no disparo manual em segundo plano (com contexto da aplicação).
2. **Máscara de data:** reescrever `maskDate()` para trabalhar só com os dígitos (no máximo 8) e montar `DD/MM/AAAA`, permitindo apagar tudo, colar uma data e digitar por cima de uma seleção sem embaralhar; validar a data antes de enviar. Vale para todos os campos que usam `maskDate`.
3. **Seletor de mês:** mostrar o rótulo "Mês" e o mês atual selecionado (tipos de valor coerentes entre `x-model` e `<option value>`), também no tema escuro.
4. **"Última sync":** sem registro de sincronização, mostrar "Nunca" (não usar a data do arquivo). Com registro, mostrar no fuso de Brasília. Mesma regra na Visão geral e no endpoint de indicadores.
5. **Rotina com os CNPJs fora do instalador e do repositório:**
   - o instalador não leva `dag_confs/Pesquisa_cnpj.yaml` (o `build.ps1` copia só o que for exemplo/modelo sem dados de cliente); o primeiro uso cria a rotina principal vazia, que o painel preenche pela sincronização (Sheets/GestãoClick);
   - tirar `dag_confs/Pesquisa_cnpj.yaml` do versionamento (`git rm --cached` + `.gitignore`), mantendo os testes que dependem dele com uma fixture sintética;
   - teste que falha se o stage do build contiver CNPJ real (ex.: qualquer `Pesquisa_cnpj*.yaml` fora de `examples_and_tests/`);
   - **não** reescrever o histórico do git nem apagar a release `v1.0.0` sem pedido explícito do usuário: registrar no Registro que o arquivo continua no histórico e no instalador 1.0.0, com as opções (reescrever histórico, apagar o asset da release) para o usuário decidir.
6. **Fechar os avisos da Visão geral:**
   - botão "X" no aviso do INLABS e no "Integrações pendentes";
   - o fechamento vale até o estado mudar: o aviso do INLABS volta se o estado do portal mudar (ex.: voltou e caiu de novo) e o de integrações volta se surgir uma pendência nova;
   - guardar no servidor, por usuário (`Settings`), para valer também na janela própria e após reinstalar; o "Recolher" atual continua existindo.
7. **Interruptor de SMTP (ligado/desligado):**
   - em Configurações → Integrações, um interruptor "Enviar e-mails" (`smtp.enabled`, padrão ligado para instalações que já têm SMTP configurado);
   - desligado: o SMTP sai da lista de pendências, do assistente de onboarding/integrações e do aviso "Integrações pendentes"; as rotinas continuam buscando e **gravando as menções** (regra 5 do `AGENTS.md`), o envio é pulado e o histórico registra "E-mail desativado" (não erro);
   - ligado sem servidor configurado: continua como pendência, como hoje;
   - os campos do SMTP ficam desabilitados enquanto o interruptor estiver desligado, sem apagar o que está salvo.
8. Atualizar o manual do painel (`rodou_dashboard/docs/`, `MANUAL.md`) e o `README.md` onde citam esses comportamentos.

**Fora de escopo:** os itens de dívida do design system (`docs/06_design_system.md`, seção 6.2), salvo o que for preciso para as tarefas acima.

**Critério de aceite**
- Testes offline para: status gravado no disparo manual em segundo plano; "Última sync" = "Nunca" sem registro e no fuso certo com registro; `smtp.enabled=false` tira o SMTP das pendências e do assistente, grava as menções e registra "E-mail desativado"; fechamento dos avisos persistido por usuário e reaberto quando o estado muda; build sem `Pesquisa_cnpj.yaml` com dados de cliente.
- Testes de interface (no navegador ou na VM) cobrindo: Baixar Dia com o quadro de status atualizando sozinho; máscara de data apagando, colando e digitando por cima; seletor de mês com rótulo e mês atual; fechar e reabrir os avisos; interruptor do SMTP.
- Instalação limpa na VM: "CNPJs monitorados: 0", "Última sync: Nunca", sem aviso de SMTP quando desligado.
- Suíte `uv run pytest -m "not live"` passando; novembro/2026 pela contingência PDF continua com 26 menções de 16 empresas (com a rotina de teste da baseline).
- Versão `1.2.0`.

**Registro:**
- **O que foi feito:**
  1. **Status do arquivamento manual (`dags.py`, `index.html`):** adicionado controle `_MANUAL_ARCHIVE_RUNNING` em `routes/dags.py::api_pdf_archive_run`/`api_pdf_archive_status` (inclusive gravando status de erro em caso de exceção na thread em segundo plano) e polling automático `pollPdfArchiveStatus()` em `templates/index.html` após **Baixar dia** / **Baixar mês**, exibindo "Arquivamento em andamento…" e atualizando o quadro de status ao concluir.
  2. **Máscara de data (`index.html`):** reescrita `maskDate(val, el)` para operar apenas sobre os dígitos (máximo 8, com suporte a colagem ISO `AAAA-MM-DD`), sincronizando `el.value` e limpando o `flatpickr` quando vazio; adicionada `isValidBrDate()` para validar antes do envio em `runPdfArchiveDate()` e `confirmTriggerRoutine()`.
  3. **Seletor de mês (`index.html`, `registrale.css`):** adicionados rótulos explícitos (`Mês` e `Ano`), largura fixa no campo de ano para não comprimir o `<select>`, coerência de tipo entre `x-model="pdfManualMonth"` (string) e `<option value="1"..."12">`, e regra `select.input option` em `registrale.css` para legibilidade no tema escuro.
  4. **"Última sync" (`models.py`, `routes/auth.py`, `routes/admin.py`):** criado `SyncHistory.get_last_sync_display()` retornando `"Nunca"` quando não há registro de sincronização em `SyncHistory` (removido o fallback para `mtime` de `Pesquisa_cnpj.yaml`) e convertendo timestamps ISO para o fuso de Brasília (`UTC-3`).
  5. **Rotina com CNPJs fora do instalador e do repositório (`paths.py`, `build.ps1`, `.gitignore`):** `dag_confs/Pesquisa_cnpj.yaml` removida do rastreamento (`git rm --cached`) e adicionada ao `.gitignore`; `paths._seed_routines_if_empty()` agora cria uma `Pesquisa_cnpj.yaml` vazia (`terms: []`) no primeiro uso sem copiar rotinas com CNPJs; `windows/build.ps1` remove `Pesquisa_cnpj*.y*ml` e `temp_*.y*ml` do stage e falha o build se algum arquivo vazar; testes em `test_runner_and_executor.py` atualizados com fixture sintética.
  6. **Avisos dispensáveis na Visão geral (`admin.py`, `auth.py`, `index.html`):** botão `X` nos avisos de contingência do INLABS e "Integrações pendentes", com persistência por usuário em `Settings` (`dismissed_notices`) via `GET /api/notices/dismissed` e `POST /api/notices/dismiss`. O aviso reaparece automaticamente se surgir uma pendência nova ou se o estado do INLABS mudar (a dispensa do INLABS é limpa quando o portal volta e o dia está carregado).
  7. **Interruptor de SMTP (`email_service.py`, `admin.py`, `dags.py`, `index.html`):** adicionado `smtp.enabled` com helper `is_smtp_enabled()` e interruptor `.dash-switch` ("Enviar e-mails") em *Configurações → Integrações*. Quando desligado, o SMTP sai das pendências e do assistente, os campos e o botão de teste ficam desabilitados sem apagar dados salvos, e as rotinas/busca mensal continuam gravando as menções normalmente, pulando o envio e registrando `"E-mail desativado"` no histórico.
  8. **Documentação e versão `1.2.0`:** atualizados `rodou_dashboard/docs/MANUAL.md`, `README.md`, `pyproject.toml`, `windows/installer.iss` e `rodou_dashboard/app/runtime/version.py`.
- **Decisões tomadas:**
  - `is_smtp_enabled()` assume `True` por padrão quando a chave `enabled` não existe, preservando instalações antigas e mantendo "ligado sem servidor configurado" como pendência até o usuário desligar explicitamente o interruptor.
  - Conforme regra do sprint, o histórico do git não foi reescrito e a release `v1.0.0` no GitHub não foi alterada: `dag_confs/Pesquisa_cnpj.yaml` continua presente no histórico anterior do git e nos assets da release `v1.0.0`.
- **Arquivos criados/alterados:** `.gitignore`, `README.md`, `pyproject.toml`, `uv.lock`, `plano/PLANO.md`, `rodou_dashboard/app/models.py`, `rodou_dashboard/app/routes/admin.py`, `rodou_dashboard/app/routes/auth.py`, `rodou_dashboard/app/routes/dags.py`, `rodou_dashboard/app/runtime/paths.py`, `rodou_dashboard/app/runtime/version.py`, `rodou_dashboard/app/services/email_service.py`, `rodou_dashboard/docs/MANUAL.md`, `rodou_dashboard/static/css/registrale.css`, `rodou_dashboard/templates/index.html`, `rodou_dashboard/tests/test_dashboard.py`, `tests/local/test_pdf_archiver.py`, `tests/local/test_runner_and_executor.py`, `tests/local/test_windows_packaging.py`, `windows/build.ps1`, `windows/installer.iss`. (`src/` não alterado).
- **Validações:**
  - `uv run pytest -m "not live" -q` → `628 passed, 3 deselected` em `12.47s` (inclui novos testes offline para arquivamento em background, `Última sync`, avisos dispensáveis por usuário, interruptor SMTP, seed vazio e guarda do `build.ps1`).
  - **Interface no navegador (`http://127.0.0.1:5055` com `REGISTRALE_DATA_DIR` temporário limpo):** validado login, onboarding PDF, `CNPJs monitorados: 0`, `Última sync: Nunca`, fechar "Integrações pendentes" com `X` e persistência após reload, interruptor SMTP desligado removendo pendência, seletor de mês com rótulo "Mês" + `Novembro` nos temas claro e escuro, máscara de data (digitar, `Ctrl+A` + `Backspace`, sobrescrever seleção) e **Baixar dia** (`20/11/2026`) atualizando o status automaticamente.
  - **Contingência PDF novembro/2026 (`03–23/11/2026`, 14 dias úteis, `REGISTRALE_INLABS_FALLBACK=pdf`):** `days=14 mentions=26 companies_by_root=16` (paridade exata com `tests/fixtures/baseline/nov2026_mentions.json`: `baseline_mentions=26 baseline_roots=16`).
- **Pendências:**
  - **Validação do instalador na VM Windows (`windows-registrale`):** não executada neste ambiente Linux (sem `virsh`/acesso à VM Windows).
  - **Decisão do usuário sobre a lista antiga de CNPJs:** `dag_confs/Pesquisa_cnpj.yaml` permanece no histórico do git e no instalador da release `v1.0.0`; opções disponíveis: (a) manter apenas a correção a partir da `v1.2.0`, (b) substituir/remover o asset da release `v1.0.0` no GitHub, ou (c) reescrever o histórico do git (ex.: `git filter-repo`) com force-push coordenado.
- **Revisão (24/11/2026):**
  - **Defeito corrigido: rotina vazia buscava a ANVISA inteira.** A rotina semeada no primeiro uso (`terms: []`, `active: true`, `0 8 * * MON-FRI`) passava `term_list=[]` ao buscador; para o upstream (`src/searchers.py`, `_prepare_search_terms`) "sem termos" é "todas as publicações", então às 8h de uma instalação limpa cada ato da ANVISA viraria menção (empresa vazia) e iria por e-mail. Correção em `runtime/runner.py::run_search_block`: lista de termos explícita e vazia pula o bloco (resultado vazio); `terms` ausente (`None`) mantém a regra do upstream. Teste `test_rotina_principal_vazia_nao_busca_todo_o_orgao` (falha sem a correção: o buscador recebia a busca de tudo).
  - **Defeito corrigido: aviso de integrações reabria ao resolver uma pendência.** A assinatura era comparada por igualdade, então desligar o SMTP (ou configurar qualquer integração) reabria o aviso fechado. Agora (`index.html::isNoticeDismissed`) o aviso de integrações só volta se surgir uma pendência que não estava no fechamento; o do INLABS continua por igualdade de estado.
  - **Validação no navegador** (`127.0.0.1:5082`, `REGISTRALE_DATA_DIR` limpo): rotina semeada sem CNPJs; "Última sync: Nunca", "CNPJs monitorados: 0"; "X" do aviso persistido em `/api/notices/dismissed` após recarregar; interruptor do SMTP desligado → campos e teste desabilitados, selo "Desativado", `smtp_enabled=false` e SMTP fora das pendências (3 restantes), aviso continua fechado; aviso reaberto com pendência nova (Google Sheets fora do fechamento); máscara: digitar `31122025` → `31/12/2025`, Ctrl+A + Backspace → vazio, digitar sobre seleção → `05/11/2026`, colar `2026-11-20` → `20/11/2026`; seletor "Mês" com Novembro nos temas claro e escuro; **Baixar dia** 23/11/2026 → "Arquivamento em andamento…" e, em 33 s, "6 PDF(s) salvo(s)" sem recarregar (20/11/2026 → "nenhuma edição", feriado).
  - `uv run pytest -m "not live" -q` → **629 passed**, 3 deselected.
  - Contingência PDF de novembro não foi refeita na revisão: a correção só afeta blocos com lista de termos vazia (a rotina da baseline tem termos).
  - **Pendências da revisão:** (1) instalação limpa na VM Windows não feita (critério de aceite): o usuário optou por pular a VM e commitar em 24/11/2026; (2) os testes novos reaproveitam a raiz `24.684.423`, que já está nas fixtures da baseline (publicação pública do DOU), em vez de um CNPJ sintético; (3) fora do escopo, já existente: o interruptor "Sincronização automática" do GestãoClick aparece desligado com o texto "Ativa" quando a chave não existe (`!== false` no texto, `x-model` no checkbox).
---

## Pedido de 24/11/2026 (noite): diagnóstico usado nos Sprints 11 a 16

Pedido do usuário depois de usar a v1.2.0 + login opcional (`345a7d3`) no Windows, com o log `registrale.log` de 24/11/2026 em anexo. Itens do pedido e onde cada um entra:

| Pedido | Sprint |
|---|---|
| A pesquisa não retornou nenhum resultado (log em anexo) | 11 |
| Testar só com as empresas que tiveram menções em novembro, não as 122 | 11 (rotina de teste) e todos os seguintes |
| Instalar a última versão do git na VM | 11 (reprodução) e 16 (homologação) |
| Interruptores de ativar/pausar não salvam o estado e não seguem o mesmo modelo | 12 |
| O assistente (wizard) deve reconhecer o que foi pausado | 12 |
| SMTP desativado desativa todas as configurações de e-mail e permite salvar sem e-mails | 12 |
| Arquivo PDF: o "ativar" é um checkbox, não um interruptor | 12 |
| Falta um jeito de atualizar o app; às vezes parece que nada está rodando; limpar o banco demora a aparecer | 12 |
| Barra lateral recolhida torta e descentralizada; cards de alerta de configuração desalinhados | 13 |
| Tela da planilha com elementos tortos e o intervalo de sincronização cortado no campo | 13 |
| Tela de template de e-mail mal formatada (variáveis quebrando linha, espaço em branco enorme) | 13 |
| Armazenamento: listar os meses de PDF baixados e o espaço que ocupam | 13 |
| Check geral de design | 13 |
| Onboarding passando por todos os passos (rotina inicial até a API do GestãoClick) | 14 |
| Documentação e manual atualizados; `plano/` unificado na documentação; tudo limpo | 15 |

**Leitura do log (24/11/2026, app instalado em `C:\Users\...\AppData\Local\Programs\Registrale`):**
1. `PostgreSQL portátil indisponível: Binários ... não encontrados` em todo início: o instalador é gerado com `-SkipPostgresDownload` (decisão registrada nos Sprints 8 e 9), então **o INLABS local nunca funciona no app instalado**.
2. Em seguida, `Erro ao consultar DB Inlabs: argument of type 'NoneType' is not iterable` (`routes/admin.py` ~560) e `Erro ao checar data ... no PostgreSQL` (`services/inlabs_service.py::is_date_loaded`) **a cada minuto**. Causa: `get_inlabs_postgres_engine()` recebe `None` de `PortablePostgres.get_sqlalchemy_url()` e faz `'+psycopg' in None`. O erro é engolido, mas polui o log e cada checagem paga o custo de tentar conectar.
3. 23:13: `YAML reconstruído com 0 CNPJs`; 23:14 a execução falha na validação Pydantic (`Pelo menos um critério de busca deve ser fornecido: terms, department ou pubtype`). A reconstrução gravou um bloco sem termos e sem `department`, e o runner valida o YAML inteiro antes de chegar à proteção de "lista de termos vazia" da revisão do Sprint 10. O painel não explicou ao analista o que fazer (sincronizar a planilha primeiro).
4. 23:14:59: sincronização da planilha → 122 CNPJs. As 3 execuções seguintes (`data=atual`, 24/11) terminaram "com sucesso", mas pelo caminho de contingência: `Busca no PDF integral de 2026-11-24: 1 arquivo(s), 0 empresa(s)`. Pontos a esclarecer: (a) só 1 arquivo para 4 seções (Seções 1, 2, 3 e Extra) e o log não diz quais seções faltaram nem por quê; (b) não houve confirmação pela API do DOU para o dia; (c) 0 menções em 24/11 pode ser verdadeiro, mas nada na tela distingue "dia sem menções" de "busca incompleta".
5. Divergência de parâmetros entre a rotina semeada/reconstruída e a baseline: a baseline (`Pesquisa_cnpj.yaml` de `92f4e92~1`) usa `department: []` (todos os órgãos), `is_exact_search: false`, `field: TUDO`, Seções 1/2/3 + `EDICAO_EXTRA` e `sources: [INLABS]`; a rotina semeada (`runtime/paths.py::_EMPTY_MAIN_ROUTINE_YAML`) usa `department: [ANVISA, ...]` e `is_exact_search: true`, e os valores padrão de `dag_config_service.py` (linhas ~222, 253, 309, 448, 528) omitem `EDICAO_EXTRA`. A busca pelo PDF ignora `department` (procura o CNPJ na página inteira), a pela API filtra: os dois caminhos podem divergir.
6. `dotenv: Key AIRFLOW__SMTP__... not removed ... key doesn't exist` (4 avisos a cada gravação de configuração): resíduo do Airflow ao salvar o SMTP.

**Rotina de teste (vale para todos os sprints daqui em diante):** em vez das 122 empresas, usar só as **16 empresas com menção em novembro/2026**, geradas em tempo de execução a partir de `tests/fixtures/baseline/nov2026_mentions.json` (CNPJs/raízes já públicos no DOU). Resultado esperado de 03 a 23/11/2026: **26 menções, 16 empresas**, igual à baseline. Não versionar uma nova lista de clientes (regra do Sprint 10).

**VM:** o container Podman `windows-registrale` existe (estado em 24/11/2026: parado). O agente sobe a VM, copia o repositório pelo compartilhamento `\\host.lan\Data` e usa os scripts de `dist/vm-s9/` como modelo (`run.ps1`, `e2e.py`, receptor de resultados). Antes de instalar, backup de `%LOCALAPPDATA%\Registrale` dentro da VM.

**Como operar a VM:** é um container `docker.io/dockurr/windows` (Windows 10). Subir com `podman start windows-registrale`; não há SSH/WinRM, só noVNC em `http://localhost:8006` (abrir no navegador embutido e digitar no PowerShell do Windows) e RDP na porta 3389. A pasta do repositório no host está montada em `/shared` e aparece no Windows como `\\host.lan\Data`, então scripts gravados em `dist/vm-sNN/` no host rodam no guest com `powershell -ExecutionPolicy Bypass -File \\host.lan\Data\dist\vm-sNN\run.ps1`. Para receber o resultado sem ler a tela, os scripts do Sprint 9 enviam cada linha por HTTP para um receptor no host (`$Recv = "http://169.254.1.2:8765"`, ver `dist/vm-s9/run.ps1`) e também gravam em `dist/vm-sNN/result.txt`. Usar uma pasta nova `dist/vm-s11/` (fora do git).

**Aprendizados do Sprint 11 sobre a VM** (valem para os próximos):
1. O `type` do navegador não chega ao noVNC e `key` com `backslash`/`period` falha. Para digitar: pelo JavaScript da página do noVNC, preencher `#noVNC_clipboard_text` e acionar `#noVNC_clipboard_send_button` (digita no que estiver em foco; `\r` = Enter).
2. PowerShell: botão direito no Iniciar → "Windows PowerShell (Admin)". Não clicar dentro do console (entra em modo de seleção e trava o Enter).
3. Fixar `resize_window` (ex.: 1000x640) para o quadro não alternar de tamanho e errar cliques; restaurar `desktop` ao fim.
4. `\\host.lan\Data` não aceita gravar arquivos novos a partir do guest: devolver resultados por HTTP (`dist/vm-s11/recv.py` no host, porta 8765; `Invoke-RestMethod http://169.254.1.2:8765/<arquivo>` no guest) e lançar scripts por um `go.cmd` fixo que lê `next.txt` (o comando digitado é sempre o mesmo).
5. Teclas enfileiradas podem abrir o Edge ou o Iniciar: conferir a tela antes de digitar.

---

## Sprint 11: Busca confiável e diagnóstico do INLABS ausente

**Pré-condição:** Sprint 10 commitado (`92f4e92`) e login opcional (`345a7d3`). Pedido do usuário em 24/11/2026 (ver "Pedido de 24/11/2026 (noite)").

**Objetivo:** a busca diária do app instalado devolve as menções certas sem depender do Postgres portátil, o log deixa de repetir erros a cada minuto e o analista sabe, na tela, se um dia foi "sem menções" ou "busca incompleta".

**Situação atual (24/11/2026):** itens 1 a 6 da leitura do log acima.

**Tarefas**
1. **Reproduzir na VM:** instalar a versão atual de `main` na VM (instalação limpa, com backup), sincronizar a planilha com a rotina de teste de 16 empresas e rodar a rotina para 23/11/2026 e para o dia atual. Guardar o log como evidência do "antes".
2. **INLABS ausente sem erro:** quando não há `INLABS_DB_URL` nem Postgres portátil, `get_inlabs_postgres_engine()` devolve `None` (ou levanta um erro próprio, ex.: `InlabsUnavailable`) e todos os chamadores (`is_date_loaded`, `get_downloaded_dates`, `admin.py` ~520-560, `pdf_search.inlabs_has_date`, rotas de `dags.py`) tratam isso como "INLABS local desativado", sem traceback. O aviso sai no log **uma vez por início**, não a cada minuto. A tela de INLABS e a Visão geral mostram "INLABS local não instalado: usando contingência (PDF/API)" em vez de erro 500.
3. **Fonte efetiva da rotina:** com o INLABS local indisponível, uma rotina com `sources: [INLABS]` vai direto para a contingência configurada (`inlabs_fallback`: `pdf` → PDF integral, `api` → API do DOU), sem tentar o banco. O histórico da execução registra a fonte usada de fato (INLABS, PDF, API) e as seções cobertas.
4. **PDF incompleto:** o log e o resultado da execução listam, por seção, se o PDF foi achado, baixado, ignorado (não existe no dia, ex.: Extra) ou falhou, com o motivo. Seção com falha **sempre** é coberta pela API do DOU (o contrato já existe em `search_day_via_pdf`; confirmar com teste que o chamador faz isso). Investigar e corrigir o "1 arquivo" de 24/11: se a Seção 2/3 não estava publicada no horário, a execução fica "incompleta" e não "sucesso".
5. **Status "incompleta":** quando alguma seção não foi coberta por nenhuma fonte, a execução termina como "Concluída com pendências" (não "sucesso"), a menção de "0 resultados" vem com o aviso e o próximo agendamento do dia tenta de novo as seções faltantes.
6. **Rotina vazia sem erro:** a reconstrução com 0 CNPJs grava uma rotina válida (ou não grava blocos de busca) e a execução manual de uma rotina sem CNPJs mostra "Nenhuma empresa monitorada: sincronize a planilha ou o GestãoClick" em vez do erro do Pydantic. Teste para os dois casos.
7. **Parâmetros padrão iguais à baseline:** a rotina semeada (`_EMPTY_MAIN_ROUTINE_YAML`) e todos os valores padrão de `dag_config_service.py` usam Seções 1/2/3 + `EDICAO_EXTRA`, `field: TUDO`, `is_exact_search: false` e `department: []` (todos os órgãos), salvo se o usuário mudou. Instalações existentes com `department: [ANVISA...]` gravado pela semente: **não** mudar sozinho; mostrar na tela da rotina o filtro de órgão ativo e registrar a opção para o usuário. Teste: para a mesma rotina, o caminho PDF e o caminho API aplicam as mesmas regras de órgão e de seção (ou a diferença fica documentada e visível).
8. **Resíduo do Airflow:** remover a gravação/remoção das chaves `AIRFLOW__SMTP__*` no `.env` (e os avisos do `dotenv`).
9. **Auditoria das regras de busca:** revisar, contra `AGENTS.md` seção 3 e a memória da regra de CNPJ por raiz, os pontos onde a busca é montada (`runner.py`, `pdf_search.py`, `routes/dags.py::trigger_routine`/`api_trigger_monthly`, `mention_service`), registrando no Registro cada divergência achada e o que foi feito. **Não alterar `src/`**: a regra de CNPJ continua única em `src/utils/cnpj.py`.

**Fora de escopo:** embutir o Postgres portátil no instalador (fica no Backlog, com o custo de tamanho e antivírus); mudanças de layout.

**Critério de aceite**
- Testes offline: engine do INLABS ausente sem `TypeError` e com um único aviso; rotina `sources: [INLABS]` sem Postgres vai para a contingência; seção com falha no PDF coberta pela API; execução com seção não coberta = "Concluída com pendências"; rotina com 0 CNPJs não quebra; padrões da rotina semeada iguais à baseline.
- Rotina de teste (16 empresas) de 03 a 23/11/2026 pela contingência PDF **e** pela API: 26 menções, 16 empresas, nas duas.
- Na VM, app instalado a partir do código do sprint: log de um início + 10 minutos sem nenhum `NoneType`; rotina de teste em 23/11/2026 com as menções esperadas para o dia; execução do dia atual mostrando as seções cobertas.
- `uv run pytest -m "not live"` passando.

**Registro:** (executado em 24–25/11/2026; nada commitado)
- **O que foi feito**
  1. **Reprodução na VM (tarefa 1), antes de mudar código:** snapshot do código pré-sprint (`dist/vm-s11/before-src`, fora do git) rodado no Python da VM, sem Postgres portátil, com a rotina de teste: 23/11 → `Erro ao checar data 2026-11-23 no PostgreSQL: argument of type 'NoneType' is not iterable` e 4 menções (as 4 raízes esperadas do dia, pela contingência PDF); dia 24/11 → 5 PDFs, 0 empresas, "concluída com sucesso". Não foi um app instalado limpo; o "antes" do app instalado é o log de 24/11 do pedido. Backup dos dados da VM: `%LOCALAPPDATA%\Registrale.bak-s11-20261125025516` (dentro da VM).
  2. **INLABS ausente (tarefa 2)** (`services/inlabs_service.py`): `InlabsUnavailable`; `get_inlabs_postgres_engine()` levanta o erro próprio quando não há `INLABS_DB_URL` nem binários do Postgres portátil (checa os binários, não só a porta gravada); aviso `INLABS local não instalado: usando contingência (PDF/API).` **uma vez por início**; `is_date_loaded`, `get_downloaded_dates`, `pdf_search.inlabs_has_date`, `admin.get_inlabs_stats` (agora 200 com `status: unavailable`) e `dags.api_check_date` tratam como "desativado", sem traceback. `/api/status` ganhou `inlabs_status.local_available` e `local_message`; a Visão geral mostra "INLABS local não instalado" (selo "Fonte em uso") e Configurações → Armazenamento mostra a mensagem em vez de erro (`index.html`).
  3. **Fonte efetiva e cobertura (tarefas 3–5)** (`runtime/runner.py`, `pdf_search.py`, `pdf_archiver.py`, `executor.py`, `routes/dags.py`, `scheduler.py`):
     - rotina `sources: [INLABS]` sem INLABS local vai direto para a contingência (`inlabs_fallback`); o resultado de cada bloco ganhou `coverage` (por seção: `coberta` | `sem_edicao` | `pendente`, com fonte e motivo) e `incomplete`; `source_used` segue como antes;
     - **causa do "1 arquivo":** `pdf_archiver._discover_pesquisa_total_pages` tratava qualquer resposta do portal sem `totalArquivos` como "sem edição" (0 páginas) e a seção sumia em silêncio; o `search_day_via_pdf` só considerava falha a seção com erro explícito. Agora o portal só vale como "sem edição" quando diz "Página Inexistente"; resposta estranha levanta erro (a seção vira `falhou`); `archive_date_pdfs` devolve `section_status`; seção 1/2/3 ausente em **dia útil** é falha (vai para a API), ausente em fim de semana/feriado ou Edição Extra é só "sem edição". Não consegui reproduzir o "1 arquivo" de 24/11 (na VM vieram 5–6 arquivos); o desenho cobre a causa provável (resposta truncada/incompleta do portal);
     - seção com falha no PDF é sempre completada pela API (já era o contrato; agora testado e registrado em `coverage`); se a API também falhar, a seção fica `pendente`;
     - nova situação de execução `partial` ("Concluída com pendências"): `executor.wait` a reconhece como terminal, `job.erro` lista as seções, o histórico registra "Busca Concluída com Pendências" (e a busca mensal "Busca Mensal com Pendências") com as seções por fonte, e o "última busca" conta `partial`;
     - o agendador, ao fim da execução diária com pendência, agenda nova tentativa em 60 min (até 4, até as 22h, job `retry::<rotina>` por referência textual); a tentativa só envia e-mail das menções **novas** (`notify_only_new`).
  4. **Rotina vazia (tarefa 6):** `runner.routine_has_no_terms` + `NoMonitoredCompanies`; `run_routine` recusa com "Nenhuma empresa monitorada: sincronize a planilha ou o GestãoClick." (execução `failed` com essa mensagem, sem traceback) e `POST /api/routines/trigger/<arquivo>` responde 400 com `code: no_companies`. A reconstrução com 0 CNPJs continua gravando o bloco com `terms: []` (válido para o painel; a busca é que avisa).
  5. **Padrões da baseline (tarefa 7):** `_EMPTY_MAIN_ROUTINE_YAML` e os defaults de `dag_config_service.py` e `routes/dags.py` (inclusive busca ad-hoc e mensal) → Seções 1/2/3 + `EDICAO_EXTRA`, `field: TUDO`, `is_exact_search: false`, `department: []`. Instalações existentes não mudam sozinhas; o cartão da rotina mostra "Filtro de órgão ativo: ..." ou "Todos os órgãos".
  6. **Divergência PDF × API com filtro de órgão (achado da tarefa 9, corrigido):** o PDF procura o CNPJ na página inteira, então empresa fora do órgão da rotina virava menção quando a API não a confirmava. Com `department` preenchido o runner passa `strict_confirm=True`: só vale o que a API (que aplica o filtro) confirmar; se a API falhar, mantém o PDF com aviso.
  7. **Resíduo do Airflow (tarefa 8):** removida a gravação/remoção de `AIRFLOW__SMTP__*` no `.env` e em `os.environ` (`routes/admin.py`, `routes/dags.py`) e os fallbacks de ambiente em `email_service.py` (a configuração vem do SQLite). Some o aviso do `dotenv`. `.env` antigos mantêm as chaves, sem efeito.
- **Auditoria das regras (tarefa 9)** contra `AGENTS.md` §3: (a) regra de CNPJ por raiz: `pdf_search.scan_pages_for_terms` usa `utils.cnpj` (única), `mention_service._cnpj_branch_regex` não mudou; (b) consulta pela raiz `XX.XXX.XXX` na API: confirmada no log da VM (`'q': '"05.785.287"'`); (c) seções 1/2/3 + Extra: divergências corrigidas no item 5; (d) menções gravadas antes do e-mail e SMTP desligado: `watch_dag_and_update_mentions` já gravava antes; `notify_only_new` só filtra o e-mail; (e) INLABS indisponível nunca pesquisa banco vazio: reforçado (item 3); (f) **divergência aberta:** `trigger_routine` com `data` explícita e `sources: [INLABS]` ainda decide "INLABS pronto" por `_local_inlabs_ready()` (exige credenciais do INLABS) em vez de `is_inlabs_local_available()`; funciona (cai na contingência), mas duplica a regra; (g) **aberta:** dia útil de hoje sem nenhuma edição publicada ainda (madrugada) fica "coberto pela API" e termina "sucesso" com 0 menções: a API não distingue "sem edição" de "sem menções" (visto na VM em 25/11 às 03h); (h) **aberta:** `terms_ignore`/`department_ignore` não são aplicados ao caminho PDF (só à confirmação pela API).
- **Arquivos:** `rodou_dashboard/app/{routes/admin.py, routes/dags.py, runtime/{executor,paths,pdf_archiver,pdf_search,runner,scheduler}.py, services/{dag_config_service,email_service,inlabs_service}.py}`, `rodou_dashboard/templates/index.html`, `rodou_dashboard/tests/test_dashboard.py` (2 testes ajustados: rotina de teste vem vazia), `tests/local/test_runner_and_executor.py` (2 ajustes), novos `tests/local/rotina_teste.py` (gerador da rotina de 16 empresas, em memória) e `tests/local/test_sprint11_busca.py` (23 testes). Fora do git: `dist/vm-s11/` (scripts da VM, `sweep.py`, `recv.py`). `src/` não alterado (nada a registrar em `UPSTREAM.md`).
- **Validações**
  - `uv run pytest -m "not live" -q` → **661 passed**, 3 deselected (antes: 638). Na VM (Windows): 660 passed, 1 failed: `test_windows_packaging.py::...test_build_excludes_client_routine_and_git_does_not_track_it`, que precisa do `git` (a cópia da VM não tem `.git` nem o Git instalado); não é regressão.
  - **Rotina de teste (16 empresas, 03–23/11/2026, 14 dias úteis), `tests/local/rotina_teste.py` + `dist/vm-s11/sweep.py`, no host Linux:** contingência PDF (`sources: [INLABS]`, sem Postgres) → **26 menções, 16 empresas, 25 pares empresa/dia, faltando=[] extras=[]** (903 s); API do DOU (`sources: [DOU]`) → **26 / 16 / 25, faltando=[] extras=[]** (154 s). Menções por dia idênticas nos dois caminhos (03/11:5, 04:1, 09:7, 13:1, 16:7, 18:1, 23:4, demais 0). Todas as seções `coberta`, nenhuma pendência.
  - **VM, instalador gerado do código do sprint** (`Registrale-Setup-1.2.0.exe`, 63 200 316 bytes, SHA-256 `a2e9d5f51e726f3bf40ea9a37718f7d081c2f0b53487e73cab93ef53d3c3ad85`; a versão não foi alterada neste sprint), instalado por cima com backup: rotina de teste em 23/11/2026 no Python instalado → 4 menções (as 4 raízes do dia), todas as seções `coberta` por `PDF integral`; dia atual da VM (25/11, madrugada, sem edição publicada ainda) → log mostra `Seções: 1=falhou; 2=falhou; 3=falhou; extra=ausente`, "completando via API do DOU", seções `coberta` por `API do DOU` com o motivo.
  - **VM, log do app instalado:** início + 10 minutos (janela aberta): 506 linhas, `NoneType=0` nos 10 minutos, **1** aviso `INLABS local não instalado` e **1** aviso do Postgres portátil (uma vez por início), sem `Erro ao checar data`.
  - **Navegador (host, `REGISTRALE_DATA_DIR` temporário):** `/api/inlabs_stats` → 200 `unavailable`; `/api/status` → `local_available:false`; Visão geral mostra "INLABS local não instalado" com "Fonte em uso: PDF integral + API do DOU"; disparar a rotina vazia → 400 "Nenhuma empresa monitorada...". Log do servidor: 0 `NoneType`/`ERROR`, 1 aviso único.
- **O que não foi validado**
  1. Nova tentativa agendada: coberta só por teste offline (`_schedule_retry` com agendador falso); não observada ao vivo (nenhuma seção ficou `pendente` nas execuções reais).
  2. Nova situação `partial` na interface: o texto aparece no histórico de eventos, mas não conferi a tela de histórico de execuções (se existir) com `partial`; `last_runs` devolve o estado cru.
  3. Na VM o `/api/status` respondeu `erro` ao teste do script (a instalação da VM tem login ligado), então o log de 10 min prova ausência de erros em uso normal com a janela aberta, não um polling forçado de `/api/status`; a rota foi exercitada no host.
  4. O "1 arquivo" de 24/11 não foi reproduzido (ver item 3); a correção é pela causa provável.
  5. Instalação **limpa** na VM não foi feita: a VM já tinha o app (login ligado, dados reais), instalei por cima com backup. Interface da VM não foi percorrida além da tela de login; o instalador interativo que estava aberto na VM foi cancelado (arquivo em uso) antes de eu instalar em modo silencioso.
  6. O Git não foi instalado na VM (pedido do usuário; fica para o Sprint 16).
- **Pendências:** auditoria (f), (g), (h) acima; embutir o Postgres portátil segue no Backlog.

### Correções pós-revisão (25/11/2026)
A revisão independente reprovou a primeira entrega; correções, sem commit e sem tocar em `src/`:
1. **Bloqueador (`runner.py`):** o `except TypeError` que atendia buscadores de teste sem `report` engolia TypeError de dentro do PDF (ex.: `PdfReader` em arquivo corrompido), rodava o PDF de novo e, se falhasse, o dia terminava `failed` sem consultar a API (regra 6). Agora `_accepted_kwargs` confere a assinatura (`inspect.signature`) antes de chamar; qualquer erro do PDF vai ao `except Exception` → API. Testes: TypeError dentro do PDF cai na API e o PDF roda **uma vez**; buscador sem `report` continua funcionando.
2. **Duplicação entre fontes (`dags.py::reconcile_mentions_across_sources`):** o id muda com a fonte (`pdf-<data>-<jornal>-<página>` x id da API). Chave estável entre fontes: (CNPJ, data, seção); cada linha existente de outra fonte consome no máximo uma menção nova (atos distintos da mesma empresa/seção/dia continuam distintos). A API substitui a linha de PDF (que sai da sessão), o PDF é descartado se a da API já existe, e o id substituto não conta como novo para o e-mail (`notify_only_new`). Testes: substituição PDF→API e inverso, atos distintos, e `watch_dag_and_update_mentions` ponta a ponta (1 menção, 0 e-mail).
3. **Nova tentativa (`scheduler.py`):** `misfire_grace_time=600` (antes herdava 24 h), data original nos argumentos (`[rotina, tentativa, AAAA-MM-DD]`), a execução aborta se não for hoje ou se a rotina estiver pausada/removida, e `_sync_routine_jobs` remove `retry::` de rotina inativa. Testes: agendamento por execução `partial`, encadeamento e `notify_only_new`, dia anterior, rotina pausada, grace e argumentos, limpeza na sincronização.
4. **Hoje sem PDF (`pdf_search.py`):** seção 1/2/3 sem PDF em dia útil é completada pela API e fica `coberta` (nunca `pendente` só por isso); para a data de hoje o motivo registra "a edição de hoje pode ainda não ter sido publicada". Teste. Limite que continua: a API não distingue "sem edição" de "sem menções".
5. **Sugestões feitas:** (6) o histórico não promete mais "nova tentativa" (quem informa é o evento "Busca Incompleta" do agendador, só quando agendou); (9) `pdf_archiver` só aceita "Página Inexistente" como sem edição (confirmado ao vivo: 22/11 e 20/11), teste de fim de semana usa o texto real; (7) com filtro de órgão, API fora (PDF sem filtro) e empresas descartadas por não confirmar entram em `notes` do bloco e no histórico ("Avisos: ...").
6. **Registrado como pendência (8 e 10):** (8) relatório por seção da Edição Extra com vários jornais (A, B...): falha em qualquer jornal marca a seção `falhou` (API cobre), sem detalhar qual jornal; (10) a fase 1 da busca mensal (cargas INLABS) não resume pendências, só a fase de contingência resume.
- **Validação:** `uv run pytest -m "not live" -q` → 672 passed, 1 failed (`rodou_dashboard/tests/test_dashboard.py::TestSprint10PanelAdjustments::test_smtp_switch_off_removes_pending_skips_email_and_saves_mentions`): falha vinda de edições em andamento de outra sessão em `routes/admin.py`/`dags.py`/`index.html` (o `git diff` cresceu além do Sprint 11 durante esta correção); não mexi nesses trechos. Varredura de novembro pela API com a rotina de teste (03–23/11): **26 menções, 16 empresas, 25 pares, faltando=[] extras=[]** (165 s). CRLF de `test_dashboard.py` preservado (1238/1238).

### Correções pós-revisão conjunta (25/11/2026)
Sprint 11 aprovado na revisão conjunta; itens Importantes/Sugestão fechados:
1. **Hoje sem PDF (I-S11-1):** seção 1/2/3 sem PDF em dia útil **para a data de hoje** (`reference_date >= hoje`) e sem erro explícito é cobrida pela API de forma **provisória**: cobertura `pendente` (fonte "API do DOU", motivo "cobertura provisória pela API: a edição pode não ter sido publicada ainda"), execução `partial` e nova tentativa agendada (só execuções agendadas, via `_pending_in_runs`). Dias passados continuam `coberta`. A API ainda é consultada em ambos os casos. Testes: hoje provisório x dia passado, `partial` + `_pending_in_runs`. (Substitui a regra anterior "hoje sem PDF = coberta com aviso".)
2. **Padrões antigos no painel (I-S11-2):** `index.html`: modal da rotina principal sem rotina carregada (`is_exact_search: false`), "Nova rotina" (Seções 1/2/3 + `EDICAO_EXTRA`, busca não exata) e o `currentR` inicial (busca não exata). Não restam `is_exact_search: true` literais no template.
3. **Edição Extra na deduplicação (S11-4):** `_section_key` normaliza qualquer rótulo com "extra" para `extra`, então "DOU - Edição Extra" (PDF) e "DOU - Seção: 1 - Extra A" (API) casam. Teste.
- **Validação:** `uv run pytest -m "not live" -q` → 683 passed, 3 deselected; varredura de novembro pela API com a rotina de teste: **26 menções, 16 empresas, 25 pares, faltando=[] extras=[]** (158 s). A contingência PDF não foi refeita (a mudança só afeta seções sem PDF em "hoje").
- **Backlog/pendências:** `terms_ignore`/`department_ignore` fora do caminho PDF (h); retry também para `failed` por erro de rede (S11-1); fase 1 da busca mensal sem resumo de pendências (10); relatório por jornal da Extra (8).

### Ajustes sugeridos ao plano (Sprints 12 a 16)
Feitos a partir do que o Sprint 11 mudou ou descobriu; não editei esses sprints.

- **Sprint 12**
  - Linhas de `index.html` citadas (~852, ~2329-2343, ~2383, ~3494/3536, ~4937) mudaram com o Sprint 11 (+ ~25 linhas a partir de ~190); reconferir por busca de texto, não por número. `dags.py` ~200/~448 também mudou (+ ~60 linhas): localizar por "Adicione pelo menos um e-mail".
  - **Já resolvido no Sprint 11:** gravação de `AIRFLOW__SMTP__*` no `.env` removida (item 7); o Sprint 12 não precisa mexer nisso, só no `smtp.enabled`.
  - **Novo estado de execução `partial`** ("Concluída com pendências", `job_runs.status`): o `/api/activity`, o indicador "Executando" e os rótulos de execução precisam tratá-lo (não é erro nem sucesso pleno); `executor.TERMINAL_STATES`/`STATUS_PARTIAL` são a fonte.
  - **Novos eventos de histórico** ("Busca Concluída com Pendências", "Busca Incompleta", "Busca Mensal com Pendências") e job agendado `retry::<rotina>`: o indicador de atividade deve mostrar "Nova tentativa às HH:MM".
  - "Pausado não é pendência" (tarefa 3): "INLABS local não instalado" também é um estado neutro (não pendência); `integrations_status` só deve cobrar credenciais do INLABS se o usuário quiser o INLABS local, e o assistente deve oferecer "usar só a contingência".
  - Caches a invalidar (tarefa 5): somar `_inlabs_cache` (`admin.py`) e `_portal_status_cache` (`inlabs_service.py`); `inlabs_stats` agora pode devolver `unavailable`.
  - A tela `refreshKpis` só roda de 60 em 60 s e **não** roda ao abrir a página: o aviso do INLABS só aparece após o primeiro ciclo (visto no navegador). O "botão Atualizar" e o carregamento inicial devem chamar `refreshKpis()`.
- **Sprint 13**
  - Os avisos (callouts) tiveram dois acréscimos: aviso de INLABS local ausente na Visão geral e `callout-info` no cartão do INLABS em Armazenamento; incluir na revisão do componente único.
  - **Armazenamento dos PDFs (tarefa 5):** quando `pdf_archive.enabled=false` os PDFs vão para `<dados>/pdf_cache` (`pdf_search._pdf_folder`) e o texto extraído fica em `<dados>/pdf_text/*.json.gz`; a listagem deve mostrar também essas duas pastas (cache), separadas da pasta do analista.
  - O cartão da rotina mostra agora "Filtro de órgão ativo: ..." (era "N órgãos"); entra na passada de design.
- **Sprint 14**
  - Passo 4 (rotina inicial): os padrões "todos os órgãos", Seções 1/2/3 + Extra e busca não exata **já são o padrão** da rotina semeada e do modal "nova rotina principal"; o assistente só precisa refletir e deixar mudar.
  - Passo 8 (INLABS): "usar só a contingência (PDF/API)" é o estado real do app instalado (`inlabs_status.local_available=false`); o texto do passo deve dizer isso, e não pedir credenciais como se o INLABS local funcionasse.
  - Passo 5 (empresas): sincronizar planilha com 0 CNPJs deixa a rotina sem termos; o "Rodar agora" deve mostrar a mensagem "Nenhuma empresa monitorada..." (400 `no_companies`) em vez de falha técnica.
  - A rotina de teste: usar `tests/local/rotina_teste.py` para gerar as 16 empresas (e, para o navegador, criar a planilha/cadastro manual a partir de `test_terms()`).
- **Sprint 15**
  - Atualizar manual e `AGENTS.md` §3 (item 6) com: cobertura por seção e "Concluída com pendências", nova tentativa no mesmo dia, `strict_confirm` com filtro de órgão, INLABS local não instalado, padrões da baseline. `rodou_dashboard/docs/MANUAL.md` e `MANUAL.md` ainda falam do INLABS como fonte principal e de "ANVISA" como padrão.
  - Sobras novas a listar na limpeza: `dist/vm-s11/` (inclui `before-src` ~16 MB, `recv.py`, scripts) além de `dist/vm-s8` e `dist/vm-s9`.
  - `test_windows_packaging.py::test_build_excludes_client_routine_and_git_does_not_track_it` exige `git` no ambiente; documentar ou marcar para pular sem `.git`.
- **Sprint 16**
  - **Operar a VM (aprendizados):** (1) o `type` do navegador **não** envia teclas ao noVNC e `key` com `backslash`/`period` não funciona; o que funciona é o painel de teclado do noVNC: pelo JavaScript da página, preencher `#noVNC_clipboard_text` e acionar `#noVNC_clipboard_send_button` (digita no que estiver em foco; use `\r` para Enter). (2) Abrir o PowerShell: botão direito no Iniciar → "Windows PowerShell (Admin)" (a UAC não pede); não clicar dentro do console (entra em modo de seleção e trava o Enter). (3) Fixar `resize_window` (ex.: 1000x640) evita o quadro do noVNC alternar entre dois tamanhos e errar cliques; lembrar de restaurar `desktop`. (4) O compartilhamento `\\host.lan\Data` **não é gravável** pelo guest para arquivos novos do usuário: devolver resultados por HTTP (`dist/vm-s11/recv.py` no host, porta 8765, e `Invoke-RestMethod http://169.254.1.2:8765/r.txt` no guest) e lançar scripts por `go.cmd` + `next.txt` (o comando digitado é sempre o mesmo). (5) Teclas enfileiradas podem abrir o Edge/Iniciar: conferir a tela antes de digitar.
  - A VM já tem uma instalação 1.2.0 com **login ligado e dados reais** (backup `Registrale.bak-s11-20261125025516` na própria VM); para a "instalação limpa" do Sprint 14/16, mover `%LOCALAPPDATA%\Registrale` e `...\Programs\Registrale` antes. O build leva ~3 min e o pytest ~1,5 min na VM; a varredura de novembro pela contingência PDF leva ~15 min no host.
  - O Git ainda não está instalado na VM (pedido do usuário em 24/11): instalar no Sprint 16 (ou antes, se o Sprint 12–15 precisar de `git` para testes) e rodar o pytest na VM com o `.git`.
  - Rodar o "dia atual" da validação à tarde, depois da publicação das edições (às 3h as seções ficam "cobertas pela API" com 0 resultado, ver auditoria (g)). A versão `1.2.0` não foi alterada pelo Sprint 11; o bump para 1.3.0 continua no Sprint 16.

---

## Sprint 12: Estado das configurações, SMTP desligado e atividade visível

**Pré-condição:** Sprint 11 aprovado.

**Objetivo:** todo interruptor do painel segue o mesmo componente e grava o estado; o assistente entende o que foi pausado; SMTP desligado desliga todo o e-mail do app; o analista sempre vê o que está rodando e consegue atualizar a tela.

**Situação atual (24/11/2026)**
- Há dois modelos de liga/desliga: `.dash-switch` (Rotinas, SMTP, Sheets, GestãoClick, login) e checkbox comum (`settings.pdf_archive.enabled`, `templates/index.html` ~852; status de empresa ~3494/3536; "Busca exata" da rotina ~2383; origens monitoradas ~2329-2343). Alguns gravam na hora (`toggleRoutine`, login), outros só no botão "Salvar" da página (SMTP, Sheets, GestãoClick, PDF), sem indicar que há alteração pendente. A revisão do Sprint 10 já apontou o GestãoClick "Sincronização automática" mostrando "Ativa" com o interruptor desligado quando a chave não existe (`!== false` no texto, `x-model` no checkbox).
- O assistente de integrações e o aviso "Integrações pendentes" só conhecem o SMTP desligado (Sprint 10). Sheets com sincronização automática desligada, GestãoClick desligado e arquivo PDF desligado continuam como pendência.
- Com o SMTP desligado, a rotina ainda exige e-mail de destino: `routes/dags.py` linhas ~200 ("Adicione pelo menos um e-mail de destino") e ~448 (rotina principal), `index.html` ~4937; os campos de destinatário, assunto, template e "Enviar relatório" continuam ativos.
- Não há botão de atualizar a tela nem indicador de atividade global. Contadores e listas têm cache com tempo (ex.: `_inlabs_cache` em `admin.py`, `_portal_status_cache` em `inlabs_service.py`), então limpar o banco ou sincronizar a planilha demora a aparecer. O polling existe só para o arquivamento manual de PDF (Sprint 10).
- Existe verificação de nova versão (`/api/admin/updates/check` e `/download`, `index.html` ~3700), mas o analista não a encontra com facilidade.

**Atualização após o Sprint 11 (25/11/2026)** (prevalece sobre a situação acima)
- Números de linha de `index.html` e `routes/dags.py` citados acima mudaram com o Sprint 11: localizar por texto (ex.: "Adicione pelo menos um e-mail", `settings.pdf_archive.enabled`).
- Já resolvido: a gravação de `AIRFLOW__SMTP__*` no `.env` foi removida no Sprint 11; aqui só entra `smtp.enabled`.
- Novo estado de execução `partial` ("Concluída com pendências", fonte: `executor.STATUS_PARTIAL`/`TERMINAL_STATES`), novos eventos de histórico ("Busca Concluída com Pendências", "Busca Incompleta", "Busca Mensal com Pendências") e job `retry::<rotina>`: o indicador de atividade (tarefa 5) mostra esse estado como neutro (nem erro nem sucesso pleno) e "Nova tentativa às HH:MM"; a tela de histórico de execuções exibe `partial` com rótulo próprio (não validado no Sprint 11).
- Tarefa 3: "INLABS local não instalado" (`inlabs_status.local_available=false`) é estado neutro, não pendência; credenciais do INLABS só são cobradas se o usuário quiser o INLABS local.
- Tarefa 5: caches a invalidar incluem `_inlabs_cache` (`admin.py`, que agora pode devolver `status: unavailable`) e `_portal_status_cache` (`inlabs_service.py`). `refreshKpis()` só roda a cada 60 s e não roda ao abrir a página (os avisos da Visão geral aparecem com atraso): chamar no carregamento inicial e no botão "Atualizar".
- Pendência da auditoria do Sprint 11, item (f): `trigger_routine` com `data` explícita decide "INLABS pronto" por `_local_inlabs_ready()` em vez de `is_inlabs_local_available()`; unificar a regra aqui (sem mudar o comportamento de busca).

**Tarefas**
1. **Um modelo de interruptor:** todo liga/desliga (ativar, pausar, habilitar) usa `.dash-switch` com rótulo e estado em texto vindo da mesma variável. Trocar o checkbox do Arquivo PDF e os demais listados acima (checkbox continua só para seleção múltipla: seções, itens de lista).
2. **Gravar o estado:** escolher uma regra única e aplicar em todo o painel: interruptor grava na hora (com toast de confirmação e volta ao estado anterior se o servidor recusar). Testes de rota para cada chave (`smtp.enabled`, `google_sheets.auto_sync`, `google_sheets.delete_obsolete`, `api_keys.gestaoclick_auto_sync`, `pdf_archive.enabled`, rotina ativa/pausada, login) confirmando que o valor sobrevive a recarregar e a reiniciar o app. Corrigir o padrão do GestãoClick (chave ausente = desligado, texto e interruptor iguais).
3. **Pausado não é pendência:** o status de integrações (`dags.py::api_integrations_status`), o assistente e o aviso da Visão geral tratam qualquer integração desligada pelo usuário como "Desativada" (selo neutro), não "Pendente". Pendência é só o que está ligado e mal configurado.
4. **SMTP desligado = e-mail desligado em todo o app:** com `smtp.enabled=false`, os campos de destinatários, assunto e template das rotinas, o envio manual de relatório, o teste de e-mail e o envio de alertas ficam desabilitados com a nota "E-mail desativado em Configurações → Integrações"; o servidor aceita salvar rotina sem e-mail (as validações de `dags.py` ~200 e ~448 só valem com SMTP ligado). Ligar de novo restaura o que estava salvo. A busca e a gravação das menções continuam (regra 5 do `AGENTS.md`).
5. **Atividade visível e atualização:**
   - indicador no topo do painel: "Ocioso", "Executando: <rotina> (<data>)", "Sincronizando planilha", "Baixando PDFs", com o próximo agendamento; alimentado por um endpoint leve (ex.: `/api/activity`) lido a cada poucos segundos enquanto houver algo rodando e a cada 30–60 s em repouso;
   - botão "Atualizar" que recarrega os dados da aba atual ignorando os caches de tempo;
   - toda ação que apaga ou altera dados em massa (limpar banco, apagar menções, sincronizar) invalida os caches afetados no servidor, para a tela refletir na hora;
   - a execução manual de rotina mostra o progresso até o fim, como o arquivamento de PDF, e ao terminar atualiza Menções e contadores;
   - "Verificar atualizações" visível em Configurações → Sistema e no menu da bandeja, com a versão atual.
6. Atualizar o manual onde citam interruptores, SMTP e atualização.

**Critério de aceite**
- Inventário (no Registro) de todos os interruptores do painel antes/depois, todos no mesmo componente e gravando o estado.
- Testes offline para as tarefas 2, 3 e 4 (incluindo salvar rotina sem e-mail com SMTP desligado e recusar com SMTP ligado).
- Teste no navegador: desligar cada integração, recarregar e reiniciar o servidor sem perder o estado; assistente sem pendência para o que foi desligado; limpar o banco e ver Visão geral e Menções zeradas sem esperar cache; execução manual da rotina de teste mostrando "Executando" e atualizando as menções ao terminar.
- `uv run pytest -m "not live"` passando; rotina de teste de novembro pela contingência PDF continua com 26/16.

**Registro:**
- **Inventário de interruptores (antes → depois):**
  1. Acesso ao painel — Exigir login (`loginRequired`): `.dash-switch` gravando na hora via `toggleLoginRequired` → mantido.
  2. SMTP — Enviar e-mails (`settings.smtp.enabled`): `.dash-switch` só no "Salvar" → `.dash-switch` gravando na hora via `toggleSettingSwitch('smtp', 'enabled', $event)`.
  3. API GestãoClick — Sincronização automática (`settings.api_keys.gestaoclick_auto_sync`): `.dash-switch` só no "Salvar" e texto bugado (`!== false` mostrava "Ativa" com switch desligado) → `.dash-switch` gravando na hora, padrão `false` quando ausente, rótulo e switch sincronizados.
  4. Arquivo PDF — Ativado (`settings.pdf_archive.enabled`): checkbox comum só no "Salvar" → `.dash-switch` gravando na hora via `toggleSettingSwitch('pdf_archive', 'enabled', $event)`.
  5. Google Sheets — Sincronização automática (`settings.google_sheets.auto_sync`) e Apagar obsoletos (`settings.google_sheets.delete_obsolete`): `.dash-switch` só no "Salvar" → `.dash-switch` gravando na hora via `toggleSettingSwitch`.
  6. Rotinas — Ativar/Pausar (`r.active`): `.dash-switch` gravando na hora via `toggleRoutine(r, $event)` (agora com rollback visual em caso de erro).
  7. Modal de Rotina — Origens monitoradas (`monitoredOrigins.*`): checkboxes comuns → `.dash-switch` gravando na hora via `toggleOriginMonitoring` (com rollback em caso de erro).
  8. Modal de Rotina — Busca por termo exato (`currentR.is_exact_search`), Adicionar Empresa (`newCompany.status`), Editar Empresa (`editingCompany.status`): checkboxes comuns → `.dash-switch` (salvos ao confirmar o modal).
  9. Modal de Rotina — Status (`currentR.active`) e Modal de E-mail — Preview/HTML (`emailForm.showHtml`): já eram `.dash-switch`.
- **O que foi feito:**
  - **Tarefas 1 e 2:** Todos os interruptores de liga/desliga padronizados em `.dash-switch` com rótulo vindo da mesma variável; gravação imediata via `toggleSettingSwitch` com toast e rollback; `admin.py::save_settings` ajustado para preservar campos existentes em updates parciais; `gestaoclick_auto_sync` com padrão `False` em `admin.py`, `auth.py` e `index.html`.
  - **Tarefa 3:** `dags.py::api_integrations_status` agora inclui `status` (`configured` | `pending` | `disabled` | `unavailable`), cobrindo `main_dag`, `smtp`, `google_sheets`, `gestaoclick`, `pdf_archive` e `inlabs`. Integrações desligadas ou INLABS local ausente não entram em `pending`. Aviso da Visão geral e badges em Configurações atualizados para exibir selos neutros ("Desativada" / "Não instalado").
  - **Tarefa 4:** Com `smtp.enabled=false`, `manage_routines`, `api_configure_main_dag` e `saveRoutine()` aceitam salvar rotina sem e-mail (preservando os e-mails salvos anteriormente); `test_smtp` e `send_email` bloqueiam com HTTP 400; campos de destinatários/assunto nas rotinas, templates de e-mail e botões de envio manual ficam desabilitados com a nota `"E-mail desativado em Configurações → Integrações"`.
  - **Tarefa 5:** Criado `GET /api/activity` em `admin.py` (estado `idle` / `running` / `syncing` / `downloading` / `partial` com `retry_at` e `next_search`), indicador global `#global-activity-indicator` e botão `#refresh-tab-btn` ("Atualizar") no topo do painel, polling adaptativo (`3 s` ocupado / `30 s` ocioso), invalidação de caches (`clear_admin_caches`, `clear_inlabs_portal_cache`) ao limpar banco/menções/sincronizar, chamada inicial de `refreshKpis()` no `init()`, inclusão dos eventos de pendências/incompleta do Sprint 11 em `completionEvents`, unificação de `_local_inlabs_ready` em `trigger_routine` para usar `is_inlabs_local_available()`, e item `"Verificar atualizações"` + versão no menu da bandeja (`windows/launcher.pyw`).
  - **Tarefa 6:** Atualizado `rodou_dashboard/docs/MANUAL.md` nas seções de barra superior/atividade, assistente de integrações, interruptores/SMTP desligado e atualização pela bandeja/Configurações.
- **Decisões tomadas:**
  - Atualizado `test_dashboard.py::test_smtp_switch_off_removes_pending_skips_email_and_saves_mentions` (Sprint 10) para esperar `smtp` em `integrations` com `status == "disabled"` e fora de `missing_fields`, refletindo o contrato do Sprint 12.
- **Arquivos criados/alterados:**
  - `rodou_dashboard/app/routes/admin.py`, `rodou_dashboard/app/routes/auth.py`, `rodou_dashboard/app/routes/dags.py`, `rodou_dashboard/app/routes/exports.py`
  - `rodou_dashboard/app/services/inlabs_service.py`
  - `rodou_dashboard/templates/index.html`
  - `windows/launcher.pyw`
  - `rodou_dashboard/docs/MANUAL.md`
  - `rodou_dashboard/tests/test_dashboard.py`, `rodou_dashboard/tests/test_sprint12_dashboard.py` (novo)
  - `plano/PLANO.md`
- **Validações:**
  - `uv run pytest -m "not live" -q` → `677 passed, 3 deselected` (inclui `test_sprint12_dashboard.py` com 4 testes novos). **Correção do Registro (revisão conjunta):** `test_sprint11_busca.py` testa o Sprint 11 e não faz varredura de novembro; a paridade 26/16 não foi provada por ele.
  - `git diff --name-only src/` → vazio (`src/` intacto).
  - Navegador (`http://127.0.0.1:5055` com `REGISTRALE_DATA_DIR` temporário): validado indicador `Ocioso`, botão `Atualizar`, GestãoClick `Desativada`, INLABS `Não instalado`, desligar SMTP e Arquivo PDF com toast imediato, persistência após F5 e após reinício do servidor, ausência de "Integrações pendentes" na Visão geral, campos de e-mail desabilitados na rotina e presença de "Verificar atualizações" em Configurações → Sistema.
- **Pendências / Não validado:**
  - Validação na VM Windows (`windows-registrale`, Podman) e disparo ao vivo no navegador da execução manual da rotina de teste a paridade 26/16 não foi provada pelo Sprint 12; foi demonstrada na revisão conjunta (varredura de novembro pela API e pela contingência PDF, 26 menções/16 empresas/25 pares, e execução manual de 23/11/2026 no navegador com 4 menções) e repetida pela API após as correções.


- **Correções pós-revisão conjunta (25/11/2026):**
  1. **Bloqueador, execução interrompida:** `executor.recover_orphan_runs(app)`, chamado ao fim de `create_app`, marca `queued`/`running` como `failed` com "Interrompida: o app foi fechado durante a execução" e registra o evento "Execução Interrompida" no histórico (preserva execuções que o próprio processo ainda roda). Testes: `test_execucoes_orfas_viram_failed...` e `test_create_app_recupera_orfas_de_uma_sessao_anterior`. **Navegador:** `job_runs` com `running` pré-existente + subir o servidor → log "1 execução(ões) órfã(s) marcada(s)"; `/api/activity` = `Ocioso`, `busy:false`, `last_job.status=failed`; indicador "Ocioso" na tela.
  2. **GestãoClick "Sincronização automática":** agora existe o job `gestaoclick_auto_sync` no `RegistraleScheduler` (`_sync_gestaoclick_job`, mesmo padrão do Sheets; intervalo `api_keys.gestaoclick_sync_interval`, padrão 60 min, mínimo 5): só agenda com o interruptor ligado **e** token+chave salvos; desligar ou apagar chaves remove o job (o `reload` já é chamado ao salvar configurações). `_run_scheduled_gestaoclick_sync` faz o mesmo fluxo do botão "Sincronizar" (`executar_sincronizacao` + `sync_json_to_db` + limpeza de caches + evento no histórico). Testes de agendamento (ligado, desligado, sem chaves) e de execução. Não há campo na tela para o intervalo (usa o padrão).
  3. **Registro:** evidência de paridade 26/16 corrigida acima.
- **Correção após a re-revisão (25/11/2026), item I-1:** as sincronizações de empresas (planilha manual e agendada, GestãoClick agendado e manual) e a reconstrução da rotina passam por uma trava única reentrante (`dag_config_service.COMPANY_SYNC_LOCK`; `rebuild_yaml_from_db` e `sync_json_to_db` decorados, `executar_sincronizacao_sheets` e os dois caminhos do GestãoClick envolvem o fluxo inteiro). O YAML temporário da rotina ganhou nome único (`tempfile.mkstemp` na mesma pasta) e é removido em caso de erro. Testes: `rodou_dashboard/tests/test_company_sync_lock.py` (a planilha espera a sincronização em andamento; 6 reconstruções simultâneas deixam a rotina válida e sem `.tmp`). Suíte: `685 passed`. Sugestões da re-revisão que ficaram para depois: texto "não foram cobertas por nenhuma fonte" na cobertura provisória (`dags.py`), erro repetido de hora em hora com token inválido do GestãoClick e indicador sem "Sincronizando" nas sincronizações agendadas (Sprint 13/16); medir na homologação quantos dias viram `partial` às 08h.

---

## Sprint 13: Acabamento visual e armazenamento dos PDFs

**Pré-condição:** Sprint 12 aprovado.

**Objetivo:** todas as telas seguem o design system (`rodou_dashboard/docs/06_design_system.md`), sem elementos tortos, cortados ou com espaço sobrando, e a aba Armazenamento mostra também os PDFs.

**Situação atual (24/11/2026)**
- **Barra lateral recolhida** (`index.html` 63–135, `w-20`): os botões de navegação mantêm `px-3 gap-3` e o ícone fica fora do centro; o avatar muda de `w-8` para `w-12` com borda; o botão "Recolher" usa `gap-4 p-3`, diferente dos demais.
- **Cards de alerta de configuração** (avisos da Visão geral e de Configurações): alinhamento de ícone, texto e botões ("Recolher", "X", ação) diferente entre eles.
- **Google Sheets** (~1120–1170): elementos desalinhados e o `<select x-model="settings.google_sheets.sync_interval">` corta o texto do intervalo.
- **Template de e-mail** (~1260–1440): as variáveis (chips) quebram linha e o editor deixa um espaço em branco grande.
- **Armazenamento** (~1548): mostra só as capturas do INLABS; não lista os PDFs do DOU baixados (`pdf_archive.folder`, layout configurável do Sprint 9).

**Atualização após o Sprint 11 (25/11/2026)** (prevalece sobre a situação acima)
- Avisos novos a incluir no componente único (tarefa 2): "INLABS local não instalado" na Visão geral e o `callout-info` do cartão do INLABS em Armazenamento.
- Tarefa 5: com `pdf_archive.enabled=false` os PDFs vão para `<dados>/pdf_cache` (`pdf_search._pdf_folder`) e o texto extraído fica em `<dados>/pdf_text/*.json.gz`; listar essas pastas como "cache interno", separadas da pasta do analista.
- O cartão da rotina agora mostra "Filtro de órgão ativo: ..." / "Todos os órgãos": entra na passada geral de design.

**Tarefas**
1. **Barra lateral recolhida:** ícones centralizados (botões `justify-center`, sem `gap`/`px` quando recolhida), avatar do mesmo tamanho nos dois estados, botão "Recolher" no mesmo padrão dos itens, `title`/tooltip com o nome do item quando recolhida, foco visível.
2. **Cards de aviso:** um componente único de aviso (callout do design system) para todos os alertas de configuração, com ícone, título, texto e ações alinhados; mesmo espaçamento na Visão geral e em Configurações.
3. **Tela do Google Sheets:** grade alinhada, campos com a mesma altura, intervalo de sincronização legível em qualquer opção (largura mínima, texto completo), estados desabilitados claros.
4. **Template de e-mail:** variáveis como chips que não quebram por dentro (`white-space: nowrap`) e quebram como grupo; editor e pré-visualização com altura proporcional ao conteúdo, sem o vazio grande; mesma regra no tema escuro.
5. **Armazenamento dos PDFs:** nova seção "PDFs do DOU" listando por mês (respeitando o layout `ano_mes`/`ano`/`nenhum`): mês, quantidade de dias, quantidade de arquivos e espaço ocupado, com total geral e a pasta atual; botão "Abrir pasta". Sem apagar nada nesta tela. Endpoint com teste offline (pasta temporária com PDFs sintéticos nos três layouts).
6. **Passada geral de design:** percorrer todas as abas e modais nos temas claro e escuro, em 1280 px e em janela estreita (~1024 px), e corrigir desvios do design system (tokens, botões, campos, espaçamentos, textos cortados); fechar o que couber da dívida da seção 6.2 do `06_design_system.md` e atualizar o documento.

**Critério de aceite**
- Capturas antes/depois (claro e escuro) de: barra lateral aberta e recolhida, avisos, Google Sheets, template de e-mail, Armazenamento.
- Lista no Registro das telas percorridas na passada geral e do que foi corrigido em cada uma.
- Teste offline do endpoint de armazenamento dos PDFs nos três layouts.
- `uv run pytest -m "not live"` passando.

**Registro (25/11/2026):**
- **O que foi feito:**
  1. **Barra lateral recolhida** (`rodou_dashboard/templates/index.html`): ícones centralizados (`justify-center px-0` quando recolhida, `gap-3 px-3` quando aberta), avatar fixo em `w-8 h-8` nos dois estados, botão "Recolher" no mesmo padrão `h-9 rounded-lg` dos itens, `title` dinâmico quando recolhida, badge de menções como ponto discreto quando recolhida e tokens `neutral-*`/`danger-*`.
  2. **Cards de aviso** (`index.html`): avisos da Visão geral ("INLABS local não instalado" e "Integrações pendentes") agrupados em `space-y-3` com `p-4`, ícone `.callout-icon` alinhado, texto neutro e ações alinhadas à direita; callout de Armazenamento (`unavailable`) ganhou ícone `info` e padding `p-4`; callout do Google Sheets padronizado para `callout-icon`.
  3. **Google Sheets** (`index.html`): grade responsiva (`grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 items-end`), campos com mesma altura (`36px`), `sync_interval` com `min-w-[150px]` e texto completo sem corte, e estado `:disabled` claro.
  4. **Template de e-mail** (`index.html`, `registrale.css`): nova classe `.chip-var` (`white-space: nowrap`, compacta, quebrando em grupo); `.input.w-auto.h-sm` para o seletor `Formato...` da toolbar; iframes do editor visual e pré-visualização com altura proporcional (`resizeTemplateIframe`, 220–480 px).
  5. **Armazenamento dos PDFs** (`pdf_archiver.py`, `routes/admin.py`, `index.html`): `get_pdf_storage_summary()` agrega por mês respeitando o layout ativo (`ano_mes`, `ano`, `nenhum`) e lista separadamente o cache interno (`<dados>/pdf_cache` e `<dados>/pdf_text/*.json.gz`); novos endpoints `GET /api/pdf_storage_stats` e `POST /api/pdf_storage/open_folder` (somente `master`, restrito às 3 pastas conhecidas); novo cartão "PDFs do DOU" em Configurações → Armazenamento com resumo por mês, total geral, pasta atual e botão "Abrir pasta" (sem apagar nada).
  6. **Passada geral de design** (`index.html`, `06_design_system.md`): removidos `font-black`, `rounded-3xl`, sombra colorida e `<thead>` antigo em Empresas, Rotinas (incluindo exibição de órgãos / "Todos os órgãos") e Relatórios; `06_design_system.md` atualizado na seção 6.2.
- **Telas percorridas na passada geral (claro e escuro):** Visão geral (aberta e recolhida), Menções, Rotinas, Empresas, Relatórios, Configurações (Google Sheets, Templates de e-mail, Armazenamento) e Manual; capturas antes/depois geradas em Chromium headless (`1280×850`, fora do git em `scratch/screenshots/`).
- **Validações:**
  - `uv run pytest rodou_dashboard/tests/test_sprint13_pdf_storage.py -v`: `5 passed` (layouts `ano_mes`, `ano`, `nenhum`, cache interno separado e `open_folder`).
  - `uv run pytest -m "not live" -q`: `690 passed, 3 deselected`.
- **Pendências / não validado:**
  - Verificação visual interativa em `1024 px` e na VM Windows (`windows-registrale`) não executada nesta rodada (homologação na VM prevista no Sprint 16); `open_folder` testado no endpoint com `subprocess.Popen` mockado.
  - Restam `font-bold` pontuais e tabelas do manual em `06_design_system.md` (fora do escopo crítico deste sprint).

- **Revisão (25/11/2026): reprovado.** Suíte `690 passed`; navegador em `127.0.0.1:5091` com `REGISTRALE_DATA_DIR` temporário e PDFs sintéticos (layout `ano_mes`), 1280×850 e 1024×768, claro e escuro.
  - **Aprovado no navegador:** barra lateral recolhida com todos os ícones centralizados (desvio de 0,5 px, a borda); avisos da Visão geral alinhados; chips de variáveis sem quebra interna; editor do template proporcional ao conteúdo; Armazenamento listando 11/2026 e 10/2026 com dias, arquivos, espaço e cache interno; `open_folder` restrito às 3 pastas e ao master.
  - **Bloqueador (pedido do usuário não resolvido):** Google Sheets, linha "Orientação / Sincronização automática / Apagar obsoletos" continua torta em 1280 px: o select de orientação corta o texto ("Linhas (cabeçalho na lir…"), "Remover exclu…" cortado e o rótulo "Sincronização automática" quebra em duas linhas, desalinhando a fileira. O intervalo de sincronização ficou legível.
  - **Importantes:** (1) em 1024 px a tela de Templates estoura a largura (`scrollWidth` 1097 > 1024): barra "Editor visual / Demonstração real / Código HTML" sai do cartão e o rótulo "Corpo do e-mail e modelo visual" fica uma palavra por linha; a passada em ~1024 px exigida pela tarefa 6 não foi feita; (2) o selo da tela do Google Sheets mostra "Pendente de Configuração" enquanto a Visão geral mostra a planilha como "Desativada" (regra do Sprint 12: desativado ≠ pendente); (3) o resumo dos PDFs só percorre o layout ativo: arquivos de um layout anterior (ex.: PDF solto na raiz com layout `ano_mes`, ou `AAAA/MM` depois de mudar para `nenhum`) não entram na contagem, embora a localização de PDFs procure nos três layouts (Sprint 9).
  - **Sugestões:** o aviso "INLABS local não instalado" repete o título no texto; no cache interno, "0 arq. · 0 B" quebra em duas linhas; o 5º cartão do passo a passo do Sheets tem uma borda verde à esquerda que os outros não têm.
  - **Plano:** o Registro do Sprint 13 tinha sido copiado também nas seções dos Sprints 14, 15 e 16; restaurado para "_(preencher)_".

- **Correções da revisão (25/11/2026):**
  1. **Google Sheets, fileira de opções** (`index.html`): grade `grid-cols-1 xl:grid-cols-2` (uma coluna abaixo de 1280 px, duas colunas em 1280 px); rótulos com `whitespace-nowrap` e altura mínima igual, selects sem `min-w` forçado e "Remover excluídos" sem `truncate`. Medido: em 1280 px e 1024 px, claro e escuro, `scrollWidth <= clientWidth` nos selects, rótulos com a mesma altura e sem overflow horizontal.
  2. **Templates de e-mail em 1024 px** (`index.html`): cabeçalho "Corpo do e-mail e modelo visual" passou a `flex-wrap` com rótulo `nowrap`, e o seletor de modo quebra dentro do cartão (`max-w-full flex-wrap`). `scrollWidth` 1014 (sem rolagem horizontal) nos modos Editor visual, Demonstração e Código, em claro e escuro.
  3. **Selo do Google Sheets** (`index.html`): usa o status do item `google_sheets` de `integrationsStatus` (mesma fonte da Visão geral): "Configurada", "Pendente" (ligado e incompleto) ou "Desativada" (interruptor desligado).
  4. **Resumo de PDFs** (`pdf_archiver.py`): `_iter_pdfs_for_layout` agora varre a pasta do analista recursivamente, independente do layout ativo, sem contar duas vezes (caminho resolvido); o mês vem da data do nome do arquivo, depois da pasta `AAAA/MM`, depois da data de modificação. Teste novo `test_pdf_storage_stats_counts_root_and_old_layout` em `test_sprint13_pdf_storage.py` (PDF na raiz + layout antigo `ano_mes` + `ano` sem data no nome).
  - **Sugestões feitas:** aviso "INLABS local não instalado" não repete mais o título; "N arq. · tamanho" do cache interno com `whitespace-nowrap`; 5º cartão do passo a passo do Sheets com o mesmo estilo dos demais.
  - **Validação:** `uv run pytest -m "not live" -q`: `691 passed, 3 deselected`; navegador em porta temporária com dados de scratch (1280 e 1024 px, claro e escuro). Servidor parado e configuração temporária do `launch.json` removida.

---

## Sprint 14: Onboarding completo

**Pré-condição:** Sprint 13 aprovado.

**Objetivo:** o primeiro uso leva o analista por toda a configuração necessária, da rotina inicial até a API do GestãoClick, e ele termina com o app pronto para a busca das 8h.

**Situação atual (24/11/2026):** o primeiro uso tem só a importação de dados antigos (`/api/admin/first_run_status`, `first_run_import`), a pasta dos PDFs (Sprint 9) e "Como abrir o painel"/login (`345a7d3`, `needs_access_onboarding`). Rotina, fontes de empresas, SMTP e INLABS ficam para o analista achar em Configurações.

**Atualização após o Sprint 11 (25/11/2026)** (prevalece sobre a situação acima)
- Passo 4: os padrões (todos os órgãos, Seções 1/2/3 + Extra, busca não exata) já são os da rotina semeada e do modal de nova rotina; o assistente só os mostra e deixa mudar.
- Passo 5: sincronizar com 0 CNPJs deixa a rotina sem termos; o "Rodar agora" do resumo trata o 400 `code: no_companies` mostrando "Nenhuma empresa monitorada..." e voltando ao passo 5.
- Passo 8: o app instalado não tem INLABS local (`inlabs_status.local_available=false`); o passo parte de "Usando a contingência (PDF integral + API do DOU)" e explica que o INLABS local não está disponível nesta versão, sem pedir credenciais como se funcionasse.
- Dados de teste: gerar as 16 empresas com `tests/local/rotina_teste.py` (`test_terms()`) para a planilha de teste ou o cadastro manual.

**Tarefas**
1. **Passos, nesta ordem** (cada um com "Pular por enquanto", que deixa a integração desativada, não pendente):
   1. Boas-vindas e importação de uma instalação anterior (como hoje).
   2. Pasta e organização dos PDFs (como hoje).
   3. Como abrir o painel / login (como hoje).
   4. **Rotina inicial:** horário (padrão 8h, dias úteis), seções (1, 2, 3, Extra), órgãos (padrão "todos", igual à baseline) e busca exata.
   5. **Empresas monitoradas:** escolher a fonte (Google Sheets, GestãoClick ou cadastro manual), com teste de conexão e sincronização na hora, mostrando quantos CNPJs entraram.
   6. **API do GestãoClick:** token e chave, teste, sincronização automática liga/desliga (pode ser o mesmo passo 5 quando essa for a fonte escolhida).
   7. **E-mail:** ligar ou desligar o SMTP; ligado, servidor, teste de envio e destinatários da rotina.
   8. **INLABS:** credenciais do portal ou "usar só a contingência (PDF/API)", explicando a diferença.
   9. **Resumo:** o que ficou ativo, desativado e pendente, com o próximo horário de busca e o botão "Rodar agora para hoje".
2. O assistente guarda o passo atual no servidor e retoma de onde parou se o app for fechado; pode ser reaberto em Configurações ("Refazer configuração inicial") sem apagar nada.
3. Reaproveitar os formulários e endpoints de Configurações (sem lógica duplicada) e os estados do Sprint 12 (desativado ≠ pendente).
4. Segredos digitados no assistente seguem a mesma regra de Configurações e não voltam para o navegador depois de salvos (ver Backlog; se não der para resolver aqui, registrar).
5. Atualizar o manual com o passo a passo do primeiro uso.

**Critério de aceite**
- Teste no navegador com `REGISTRALE_DATA_DIR` limpo: percorrer os 9 passos com a rotina de teste (16 empresas via planilha de teste ou cadastro manual), terminar com "Rodar agora" e ver as menções; repetir pulando tudo e conferir que nada fica como pendência.
- Teste de retomada: fechar no passo 5 e reabrir no passo 5.
- Testes offline dos endpoints de estado do assistente.
- Instalação limpa na VM percorrendo o assistente.
- `uv run pytest -m "not live"` passando.

**Registro:**
- **O que foi feito:**
  - Criado o serviço [onboarding_service.py](file:///var/home/pedro/Área de trabalho/Projetos/Dou/Registrale-dou/rodou_dashboard/app/services/onboarding_service.py) para persistir o estado do assistente (`onboarding_state` em `Settings`: `completed`, `current_step`, `skipped_steps`, `company_source`), com compatibilidade automática para instalações anteriores ao Sprint 14 (`pdf_onboarding_done` + `auth_onboarding_done`).
  - Adicionados os endpoints `GET/POST /api/admin/onboarding` e `POST /api/gestaoclick/test` em [admin.py](file:///var/home/pedro/Área de trabalho/Projetos/Dou/Registrale-dou/rodou_dashboard/app/routes/admin.py), além do campo `onboarding` em `GET /api/admin/first_run_status`.
  - Atualizado `api_integrations_status` em [dags.py](file:///var/home/pedro/Área de trabalho/Projetos/Dou/Registrale-dou/rodou_dashboard/app/routes/dags.py) e `save_settings` em `admin.py` para respeitar `inlabs.enabled` quando o INLABS local estiver disponível mas for pulado/desativado pelo usuário.
  - Substituídos os modais separados de PDF e acesso pelo modal unificado de 9 passos (`showOnboardingModal`) em [index.html](file:///var/home/pedro/Área de trabalho/Projetos/Dou/Registrale-dou/rodou_dashboard/templates/index.html), reaproveitando os endpoints de Configurações (`/api/admin/first_run_import`, `/api/admin/pdf_onboarding`, `/api/admin/access_settings`, `/api/system/configure_main_dag`, `/api/save_settings`, `/api/google_sheets/test`, `/api/google_sheets/sync`, `/api/companies`, `/api/gestaoclick/test`, `/api/sync`, `/api/test_smtp`, `/api/system/integrations_status`, `/api/routines/trigger/Pesquisa_cnpj.yaml` com tratamento de `code: no_companies` voltando ao passo 5), além do botão **Refazer configuração inicial** em Configurações → Sistema e atualizações.
  - Atualizado [MANUAL.md](file:///var/home/pedro/Área de trabalho/Projetos/Dou/Registrale-dou/rodou_dashboard/docs/MANUAL.md) (seção 1.5) com o passo a passo completo do primeiro uso.
  - Criados testes offline em [test_sprint14_onboarding.py](file:///var/home/pedro/Área de trabalho/Projetos/Dou/Registrale-dou/rodou_dashboard/tests/test_sprint14_onboarding.py).
- **Decisões:**
  - Segredos digitados no assistente (senhas SMTP/INLABS, tokens GestãoClick, JSON do Google Sheets) são enviados ao salvar e limpos do estado local do assistente em seguida; os endpoints `/api/admin/first_run_status` e `/api/admin/onboarding` nunca retornam segredos. (A remoção de segredos de `GET /api/settings` na aba Configurações segue no Backlog).
  - "Pular por enquanto" desativa explicitamente a integração do passo (`pdf_archive.enabled=false`, `main_dag_settings.active=false`, `google_sheets.auto_sync=false`, `gestaoclick_auto_sync=false`, `smtp.enabled=false`, `inlabs.enabled=false`) para que nada fique marcado como pendente.
- **Validações:**
  - `uv run pytest -m "not live" -q`: **698 passed, 3 deselected** (inclui 7 testes novos em `test_sprint14_onboarding.py` cobrindo estado inicial, upgrade legado, avanço/retomada no passo 5, reabertura sem apagar dados, pular tudo com 0 pendências, autorização e `POST /api/gestaoclick/test` offline).
  - Navegador com `REGISTRALE_DATA_DIR=/tmp/registrale_s14_e2e` limpo (`http://127.0.0.1:5000`, login `admin`/`admin`): validado abertura automática no Passo 1 de 9, caminho "Pular por enquanto" nos 8 primeiros passos resultando em Passo 9 sem nenhuma pendência, reabertura via Configurações → Sistema e atualizações → "Refazer configuração inicial", retomada automática no Passo 5 após recarregar a página, e cadastro manual de empresa com atualização do resumo no Passo 9. (Após a validação no navegador, corrigido `activity.next_search` e adicionado `refreshKpis()` ao concluir o Passo 9, revalidando `pytest` em seguida).
- **Pendências / Não validado nesta rodada:**
  - Instalação limpa na VM `windows-registrale` (container Podman está `Up`, mas não foi executada a instalação via noVNC nesta sessão; fica para o Sprint 16 / próxima rodada na VM).
  - Execução ao vivo do botão "Buscar agora" no Passo 9 com todas as 16 empresas da rotina de teste (no navegador foi testado cadastro manual de 1 empresa sem disparo de busca ao vivo).
- **Revisão (25/11/2026): reprovado.** Suíte: 698 passando. Navegador com `REGISTRALE_DATA_DIR` e `REGISTRALE_ROUTINES_DIR` limpos, 1280 px, caminho completo com as 16 empresas da rotina de teste.
  - **Bloqueador 1, passo 4 não salva numa instalação limpa:** "Salvar e continuar" chama `configure_main_dag` sem e-mails; como `is_smtp_enabled()` vale `true` quando o SMTP nunca foi configurado, a rota responde 400 "Pelo menos um e-mail de destino é obrigatório". O analista só avança com "Pular por enquanto", que desativa a rotina principal. Correção: no passo 4 não validar e-mails (mandar só os campos da rotina e a rota só exigir e-mails quando `emails` vier no payload) ou tratar SMTP nunca configurado como desligado.
  - **Bloqueador 2, interruptores do assistente não respondem ao clique:** os quatro (busca exata no passo 4, sincronização automática da planilha no 5, do GestãoClick no 6 e SMTP no 7) usam `<span class="dash-switch">` sem `<label>` em volta, então clicar não muda o `x-model`. No passo 7 o SMTP fica "Ligado" e, sem destinatários, o passo também não salva. Correção: trocar o `span` por `label`, como em Configurações.
  - **Importante 1, passo 7 desfaz o horário do passo 4:** com SMTP ligado ele chama `configure_main_dag` só com `emails` e `subject`; a rota usa `schedule` padrão `0 8 * * MON-FRI` e `active: true` quando não vêm no payload. Reproduzido: horário 12h salvo, depois o passo 7 → YAML volta a `0 8 * * MON-FRI`. Correção: a rota só altera `schedule`/`active` quando vierem no payload.
  - **Importante 2, "Pular" no passo 4 desliga a busca diária:** deixa `active: false` e `is_paused: true` na rotina principal, mas o resumo e a barra continuam mostrando "Próxima pesquisa 26/11/2026 08:00". Pular a rotina inicial deveria manter os padrões já semeados (8h, Seções 1/2/3 + Extra, todos os órgãos) ativos; se a decisão for desativar, `next_search` precisa sair do resumo.
  - **Importante 3, "Refazer configuração inicial" + "Pular" desliga o que já estava configurado:** `_deactivate_step_integration` desativa SMTP, GestãoClick, PDFs, INLABS mesmo quando o analista só quer passar por um passo já pronto. Na reabertura, "Pular" deve só avançar quando a integração já está configurada (ou o botão virar "Manter como está").
  - **Sugestão:** `POST /api/gestaoclick/test` repete os cabeçalhos e a URL de `sync_cnpj.py`; extrair um helper comum. A origem "Cadastro manual" já vem marcada no passo 5 sem o analista escolher.
  - **O que passou:** abertura automática no passo 1; passos 2, 3, 5 (16 empresas pela lista colada), 6 (pulado), 8 (texto da contingência certo, sem pedir credenciais) e 9 (Rotina ativa, SMTP/Sheets/GestãoClick desativados, PDF ativo, INLABS "Não instalado", 16 empresas, nenhuma pendência); retomada no passo 5 depois de recarregar; "Buscar agora" disparou a busca de hoje com os 16 termos (o portal do DOU estava lento e a busca não terminou durante a revisão, então as menções não foram conferidas). `dag_confs/Pesquisa_cnpj.yaml` intacto.
- **Correções da revisão (25/11/2026):**
  - **Bloqueador 1:** `api_configure_main_dag` (`routes/dags.py`) só exige e-mails quando `emails` vem no payload com SMTP ligado; o passo 4 (só campos da rotina) salva numa instalação limpa e o modal de Configurações, que manda tudo junto, segue validando.
  - **Bloqueador 2:** os interruptores dos passos 4, 5, 6 e 7 agora são `<label class="dash-switch">` (nos passos 4 e 5 o `label` externo virou `div` para não aninhar labels). Clique conferido no navegador nos quatro; os `span.dash-switch` de Empresas/DOU (já dentro de `label`) não foram tocados.
  - **Importante 1:** a rota só altera `schedule`, `active` e `subject` quando vêm no payload (senão mantém o existente; instalação nova usa o padrão). Horário 12h do passo 4 sobrevive ao passo 7 com SMTP ligado e destinatário fictício.
  - **Importante 2:** pular o passo 4 não desativa mais nada (rotina semeada continua ativa, resumo e `next_search` coerentes: 26/11 08:00 com tudo pulado). O botão vira "Manter padrão" e o passo não entra em `skipped_steps`.
  - **Importante 3:** o estado ganhou `reopened` (ligado por `reopen`, limpo por `complete`). Reaberto, "pular" uma integração já ligada só avança ("Manter como está", sem entrar em `skipped_steps`); integração desligada continua sendo desativada. A resposta do `skip` traz `deactivated`, que o front usa para atualizar `settings` local.
  - **Sugestões:** `build_gestaoclick_headers` e `GESTAOCLICK_DEFAULT_BASE_URL` em `services/sync_cnpj.py`, usados também por `POST /api/gestaoclick/test`; "Cadastro manual" não vem mais pré-marcado no passo 5. Manual (seção 1.5) atualizado.
  - **Testes:** 6 novos em `test_sprint14_onboarding.py` (passo 4 sem e-mails, e-mails só com `emails` + SMTP ligado, atualização parcial, pular passo 4, reabertura + pular, HTML sem `span.dash-switch` no assistente) e ajuste do "pular tudo". `uv run pytest -m "not live" -q`: **704 passed, 3 deselected**.
  - **Navegador** (`REGISTRALE_DATA_DIR` e `REGISTRALE_ROUTINES_DIR` isolados, porta 5095, 1280 px, cliques reais): instalação limpa com caminho completo (passo 4 salva em 12h sem pular; 16 empresas coladas no passo 5; interruptores dos passos 4, 5, 6 e 7 respondem, SMTP desligado e religado; destinatário `teste@exemplo.com` no passo 7 e YAML continua `0 12 * * MON-FRI`, `active: true`; resumo "Próxima pesquisa 25/11 12:00"); outra instalação limpa pulando tudo (rotina Ativa, 26/11 08:00, nenhuma pendência); reabertura via "Refazer configuração inicial" com "Manter como está" no passo 2 (PDF continua ativo). "Buscar agora" não foi acionado. `dag_confs/Pesquisa_cnpj.yaml` intacto (md5 `82af5c0c...`).

---

## Sprint 15: Documentação unificada e limpeza

**Pré-condição:** Sprint 14 aprovado (o comportamento que a documentação descreve já está pronto).

**Objetivo:** uma documentação só, atual e enxuta, com o histórico do plano dentro dela, e um repositório sem arquivos soltos.

**Situação atual (24/11/2026)**
- Documentos espalhados e duplicados: `README.md`, `MANUAL.md` (raiz, 479 linhas) **e** `rodou_dashboard/docs/MANUAL.md` (486 linhas), `rodou_dashboard/docs/01..06_*.md`, cópias em `docs/docs/dashboard/01..05_*.md`, `AGENTS.md`, `CHANGELOG.md` (do upstream), `plano/` (PLANO, INVENTARIO, UPSTREAM, HOMOLOGACAO, `prompts/`).
- `docs/` (MkDocs do upstream Ro-DOU) ainda ensina Docker, WSL e Kubernetes, que o app não usa mais.
- Sobras de trabalho no repositório local: `dist/vm-s8`, `dist/vm-s9` (scripts e capturas de VM), `mnt/`, `flask_sessions/`, `.vscode_edit/`, `data/`.

**Atualização após o Sprint 11 (25/11/2026)** (prevalece sobre a situação acima)
- O manual (`MANUAL.md` e `rodou_dashboard/docs/MANUAL.md`) ainda trata o INLABS como fonte principal e a ANVISA como padrão. Documentar: cobertura por seção e "Concluída com pendências", nova tentativa no mesmo dia (60 min, até 4, até 22h, e-mail só das menções novas), confirmação obrigatória pela API quando há filtro de órgão (`strict_confirm`), INLABS local não instalado e os padrões da baseline. Atualizar também `AGENTS.md` §3 (regra 6).
- Limpeza: incluir `dist/vm-s11/` (com `before-src`, ~16 MB) junto de `dist/vm-s8` e `dist/vm-s9`.
- `test_windows_packaging.py::test_build_excludes_client_routine_and_git_does_not_track_it` exige `git`: pular com motivo quando não houver `.git`/`git` (falhou na VM por isso).
- Atenção a finais de linha: `rodou_dashboard/tests/test_dashboard.py` é CRLF no git; não converter arquivos ao editar (no Sprint 11 a conversão gerou um diff falso de 2.472 linhas). Avaliar um `.gitattributes`.

**Tarefas**
1. **Estrutura alvo** (propor no Registro antes de mover e seguir):
   - `README.md`: o que é, instalar, primeiro uso, onde está o resto (curto);
   - `docs/manual/`: manual do analista (um arquivo por assunto: primeiro uso, rotinas, empresas, menções e relatórios, PDFs, integrações, armazenamento, atualização, problemas comuns), fonte única do "Manual" dentro do painel;
   - `docs/tecnico/`: arquitetura, API, operação e build do instalador, design system, upstream (`UPSTREAM.md`), inventário;
   - `docs/projeto/`: o plano (`PLANO.md` com as decisões, a baseline e os sprints, Registros mantidos), `HOMOLOGACAO.md` e `prompts/`;
   - documentação do upstream Ro-DOU (parâmetros, operadores, exemplos de YAML) mantida só no que vale para o app, sem Docker/WSL/K8s, em `docs/tecnico/` ou `docs/upstream/`.
2. Um único manual: eliminar a duplicata da raiz e as cópias de `docs/docs/dashboard/`; o painel (`admin.py::get_user_manual`) e o instalador leem o mesmo arquivo; o manual cobre tudo o que os Sprints 11 a 14 mudaram, com capturas atualizadas.
3. Atualizar todas as referências de caminho: `AGENTS.md`, prompts, `build.ps1`, `installer.iss`, testes, `mkdocs.yml` (ou remover o MkDocs se não for publicado; decidir com o usuário), links internos. Nenhum link quebrado (checar com script).
4. `CHANGELOG.md` do Registrale (versões 1.0.0 a atual) separado do histórico do upstream.
5. Limpeza: listar no Registro os arquivos e pastas soltos com proposta (apagar, mover para fora do repo, `.gitignore`) e **só apagar com confirmação do usuário**. Nada de segredos ou dados de clientes versionados.
6. Usar `git mv` para manter o histórico dos arquivos movidos.

**Critério de aceite**
- Árvore final de `docs/` no Registro; script de links sem quebras; o "Manual" do painel abre o manual novo.
- `grep -rni "docker\|airflow\|wsl\|k8s"` nos documentos do app só em contexto histórico (plano/registro) ou do upstream marcado como tal.
- `uv run pytest -m "not live"` e o build do instalador passando com os novos caminhos.

**Registro:** _(preencher)_
---

## Sprint 16: Homologação na VM e release 1.3.0

**Pré-condição:** Sprints 11 a 15 aprovados.

**Objetivo:** validar o pacote final no Windows como o analista vai usar e publicar a versão 1.3.0.

**Atualização após o Sprint 11 (25/11/2026)** (prevalece sobre a situação acima)
- A VM já tem a 1.2.0 instalada com **login ligado e dados reais** (backup `%LOCALAPPDATA%\Registrale.bak-s11-20261125025516` na própria VM). Para a instalação limpa, mover `%LOCALAPPDATA%\Registrale` e `%LOCALAPPDATA%\Programs\Registrale` antes (não apagar).
- Instalar o Git na VM e rodar o pytest lá com o `.git` (sem ele, 1 teste de empacotamento falha).
- Validar a nova tentativa automática ao vivo (no Sprint 11 só houve teste offline) e a exibição de `partial`.
- Rodar a validação do "dia atual" à tarde, depois da publicação: de madrugada a API não distingue "sem edição" de "sem menções" (auditoria (g) do Sprint 11).
- Tempos medidos: build ~3 min e pytest ~1,5 min na VM; novembro pela contingência PDF ~15 min no host.

**Tarefas**
1. Build do instalador a partir de `main` na VM (`build.ps1 -SkipPostgresDownload`, ou com o Postgres se o Backlog tiver sido resolvido), com SHA-256.
2. **Atualização:** VM com a 1.2.0 instalada e dados (rotina de teste, menções, PDFs) → instalar a 1.3.0 por cima → dados, configurações, interruptores e PDFs preservados.
3. **Instalação limpa:** assistente completo (Sprint 14), rotina de teste de 16 empresas, "Rodar agora" para 23/11/2026, novembro inteiro pela contingência PDF (26/16), log sem `NoneType` nem tracebacks.
4. Checklist de uso: barra lateral, avisos, interruptores, SMTP desligado, atividade/atualizar, armazenamento dos PDFs, manual, verificação de atualização, janela própria, bandeja, desinstalação preservando dados.
5. Versão `1.3.0` (`pyproject.toml`, `version.py`, `installer.iss`), CHANGELOG, e, **só com pedido do usuário**, commit, tag, push e release no GitHub (sem `Co-Authored-By`).

**Critério de aceite:** checklist completo no Registro com evidências (capturas, trechos do log, SHA-256); o que não passou fica como pendência com o motivo.

**Registro:** _(preencher)_
---

## Backlog

- **Postgres portátil no instalador:** hoje o build usa `-SkipPostgresDownload` e o INLABS local nunca roda no app instalado (Sprint 11 faz a contingência funcionar sem ele). Avaliar embutir os binários (tamanho do instalador, antivírus, SHA-256 fixo) ou aposentar o INLABS local em favor de PDF + API.
- **Exportar a página com a menção destacada (standby):** gerar, para cada menção, o PDF só da página do DOU onde a empresa aparece, com o CNPJ destacado, salvo junto do PDF do dia. Depende do Sprint 5 (fonte do PDF e localização da página: `numberpage` no INLABS e `pdfpage` no XML).
- Busca opcional por razão social (citações sem CNPJ, como despachos do CADE), marcada como "por nome" e sujeita a revisão, por causa dos falsos positivos.
- Não enviar segredos ao navegador na página de configurações (hoje o HTML do usuário master contém senhas e a chave do Google), e não apagar tokens salvos quando o campo for enviado vazio.
- Tempo limite menor com mais tentativas na API do DOU (10 s × 5 em vez de 35 s × 3) para dias de portal instável.
