# Procedimento de sincronização com o Ro-DOU oficial (upstream)

O Registrale-DOU é um fork do [Ro-DOU](https://github.com/gestaogovbr/Ro-dou) (`remote upstream`). Este documento define como trazer atualizações do upstream, registra todos os patches locais em arquivos do upstream e lista os caminhos removidos pelo projeto.

---

## 1. Procedimento de merge

1. Garanta que a árvore de trabalho está limpa (`git status --short` vazio) e que você está na branch de trabalho (ex.: uma branch temporária de sync a partir de `feature/modo-local` ou `main`).
2. Execute o script auxiliar:

   ```bash
   uv run python tools/sync_upstream.py
   ```

   O script:
   - Faz `git fetch upstream`;
   - Executa `git merge --no-commit --no-ff upstream/main`;
   - Mantém a nossa versão (`--ours`) de `AGENTS.md`, `README.md` e `CHANGELOG.md` (incorporando manualmente só o que for útil depois);
   - Re-remove os caminhos listados na seção 3 deste documento (`REMOVED_PATHS` em `tools/sync_upstream.py`);
   - Se não houver conflitos pendentes, roda `uv run pytest -m "not live and not airflow"`;
   - Imprime o relatório final de conflitos, remoções e testes.

3. Se houver conflitos em arquivos com patches locais (seção 2), resolva preservando os patches registrados abaixo e rode `uv run pytest -m "not live and not airflow"`.
4. Se o upstream passar a importar algum símbolo novo de `airflow.*` em `src/`, o teste `tests/local/test_shim_imports.py` falhará indicando exatamente o símbolo faltante — amplie `compat/airflow_shim/`, **não** edite os arquivos de `src/`.
5. Revise o diff (`git diff --cached`) e finalize o commit de merge (`git commit`) somente quando todos os testes passarem.

---

## 2. Patches locais em arquivos do upstream

Todo patch local em arquivo do upstream deve ser pequeno, comentado em português e registrado aqui.

| Arquivo | Motivo | Resumo do patch / como reaplicar |
|---|---|---|
| `src/utils/cnpj.py` | Regra de negócio: identificação por raiz de CNPJ (8 primeiros dígitos), raiz pontuada isolada (ANVISA), proteção contra valor monetário/número maior e suporte a CNPJ alfanumérico | Módulo **local novo** (não existe no upstream). Manter integralmente em conflitos. |
| `src/searchers.py` | Consulta na API do DOU por raiz formatada (`XX.XXX.XXX`), filtragem de falsos positivos por raiz/estabelecimento e marcação de `matched_cnpj`, `is_branch` e `root_only` | Importa `cnpj_root`, `extract_cnpj_matches`, `format_root_for_dou_query`, `is_cnpj` de `utils.cnpj` e aplica `extract_cnpj_matches` nos resultados do `DOUSearcher`. |
| `src/hooks/dou_hook.py` | Resiliência contra bloqueio/lentidão do portal `in.gov.br` (User-Agent, `Accept-Language`, timeout/tentativas configuráveis via `REGISTRALE_DOU_TIMEOUT` e `REGISTRALE_DOU_MAX_RETRIES`, padrão 10s × 5 com backoff) | Preservar `_request_page` lendo `REGISTRALE_DOU_TIMEOUT` (padrão `10`) e `REGISTRALE_DOU_MAX_RETRIES` (padrão `5`) e headers compatíveis com navegador. |
| `src/hooks/inlabs_hook.py` | Identificação por raiz de CNPJ nos resultados do INLABS e proteção contra `None` / apóstrofo em termos | Preservar chamadas a `utils.cnpj` (`cnpj_root`, `extract_cnpj_matches`) e tratamento seguro de strings. |
| `src/hooks/inlabs_hook_sql_mode.py` | Busca SQL no PostgreSQL usando padrão de raiz de CNPJ (`company_sql_pattern`) | Importa `cnpj_root` e `company_sql_pattern` de `utils.cnpj` e aplica na montagem das queries SQL. |
| `src/schemas.py` | Tolerância a listas vazias/nulas geradas pelo painel no YAML e `report` opcional em `DAGConfig` | Preservar `_drop_empty_items`, os `@field_validator(..., mode="before")` em `SearchConfig`/`ReportConfig` e `report: Optional[ReportConfig]` com `default_factory=ReportConfig`. |

> Nota: `src/dou_dag_generator.py` e `dag_load_inlabs/ro_dou_inlabs_load_pg_dag.py` foram removidos no Sprint 8 (lógica portada para `rodou_dashboard/app/runtime/runner.py` e `inlabs_loader.py`; `init-db.sql` movido para `rodou_dashboard/app/runtime/sql/init-db.sql`). `src/utils/open_search/` foi mantido porque `src/hooks/inlabs_hook.py` do upstream o importa.

---

## 3. Caminhos removidos

Lista de caminhos do upstream removidos por decisão do projeto (re-removidos automaticamente pelo `tools/sync_upstream.py` após cada merge):

- `Dockerfile`, `docker-compose.yml`, `docker-compose.override.yml`, `.dockerignore`
- `Makefile`, `Makefile.backup`, `generate-Makefile.sh`, `instalar.bat`
- `rodou_dashboard/Dockerfile`, `docs/Dockerfile`, `docs/docker-compose.yml`
- `helm/`
- `src/dou_dag_generator.py`
- `dag_load_inlabs/`
- `tests/dag_generator_test.py`, `tests/dag_generator_invalid_yaml_test.py`, `tests/test_dag_loading.py`, `tests/test_e2e_dag_execution.py`
- `.github/workflows/ci-tests.yml`, `.github/workflows/docker_build_and_publish.yml`
- `.env.example` (configuração do Airflow/Docker) e `requirements-uninstall.txt` (imagem Docker), removidos na revisão do Sprint 8
- MkDocs e documentação do upstream sobre Docker, WSL, Kubernetes e Airflow removidos no Sprint 15 (workflows `.github/workflows/gh_pages.yml`, que publicava o MkDocs, e `.github/workflows/update_changelog.yml`, que editava `docs/mkdocs.yml` e `docs/version.txt`; o `CHANGELOG.md` antigo do Ro-DOU ficou em `docs/upstream/CHANGELOG.md`; os guias de pesquisa aplicáveis ao Registrale foram movidos para `docs/upstream/`): `docs/mkdocs.yml`, `docs/index.html`, `docs/overrides/`, `docs/version.txt`, `docs/docs/`, `docs/img/Makerun.png`, `docs/img/makerunwsl.png`, `docs/img/new_make_run.png`, `docs/img/exemplo-dag-doc_md.png`, `docs/img/fluxo_add_opensearch.png`, `docs/img/rodou_arquitetura.excalidraw`, `docs/img/rodou_arquitetura.png`, `docs/img/rodou_arquitetura.svg`
