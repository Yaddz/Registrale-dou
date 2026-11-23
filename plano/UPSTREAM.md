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
   - Mantém a nossa versão (`--ours`) de `AGENTS.md` e `README.md` (incorporando manualmente só o que for útil depois);
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
| `src/hooks/dou_hook.py` | Resiliência contra bloqueio/lentidão do portal `in.gov.br` (User-Agent, `Accept-Language`, timeout de 35s, `max_retries=3` com backoff) | Preservar `_request_page` com `timeout = 35`, `max_retries = 3` e headers compatíveis com navegador. |
| `src/hooks/inlabs_hook.py` | Identificação por raiz de CNPJ nos resultados do INLABS e proteção contra `None` / apóstrofo em termos | Preservar chamadas a `utils.cnpj` (`cnpj_root`, `extract_cnpj_matches`) e tratamento seguro de strings. |
| `src/hooks/inlabs_hook_sql_mode.py` | Busca SQL no PostgreSQL usando padrão de raiz de CNPJ (`company_sql_pattern`) | Importa `cnpj_root` e `company_sql_pattern` de `utils.cnpj` e aplica na montagem das queries SQL. |
| `src/schemas.py` | Tolerância a listas vazias/nulas geradas pelo painel no YAML e `report` opcional em `DAGConfig` | Preservar `_drop_empty_items`, os `@field_validator(..., mode="before")` em `SearchConfig`/`ReportConfig` e `report: Optional[ReportConfig]` com `default_factory=ReportConfig`. |
| `src/dou_dag_generator.py` | Tolerância a YAML inválido sem travar as demais DAGs e suporte a DAGs temporárias sem agenda | Preservar apenas enquanto o modo Docker existir; **será removido no Sprint 8**. |
| `dag_load_inlabs/ro_dou_inlabs_load_pg_dag.py` | Detecção de página de "Manutenção Programada" do INLABS e ajustes de carga/Datasets | Preservar apenas enquanto o modo Docker existir; lógica portada para `rodou_dashboard/app/runtime/inlabs_loader.py` no Sprint 4 e arquivo **removido no Sprint 8**. |

> Nota do Sprint 1: `src/` não foi alterado neste sprint (`git diff baseline-docker -- src/` vazio). A execução fora do Airflow ocorre via `compat/airflow_shim/` e `compat/bootstrap.py`.

---

## 3. Caminhos removidos

Lista de caminhos do upstream removidos por decisão do projeto (re-removidos automaticamente pelo `tools/sync_upstream.py` após cada merge):

- _(vazia até o Sprint 8 — os modos Docker e local convivem até a aprovação do Sprint 7)_
