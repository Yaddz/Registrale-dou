# Prompt: Sprint 8: Remoção de Docker/Airflow, limpeza do git e novo README

Você vai executar o **Sprint 8: Remoção de Docker/Airflow, limpeza do git e novo README** da migração do Registrale-DOU para aplicativo Windows.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro: regras de trabalho, regras de negócio (seção 3) e compatibilidade com o upstream (seção 4).
2. `plano/PLANO.md`: seções "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 8"**. Consulte o plano sempre que tiver dúvida de escopo; ele prevalece sobre este prompt.
3. `plano/HOMOLOGACAO.md`. **Se não houver aprovação registrada pelo usuário, pare aqui e avise.**
4. `plano/UPSTREAM.md`.

Objetivo: deixar o repositório só com o aplicativo Windows, mantendo a capacidade de receber atualizações do Ro-DOU oficial.

Passos principais (detalhes no plano):
1. Remova os artefatos de Docker, Airflow e Kubernetes listados no plano. A lógica da carga INLABS já está em `runtime/inlabs_loader.py`; antes de apagar `dag_load_inlabs/`, mova `sql/init-db.sql` para o runtime e atualize `pg_portable`. **Não remova** `src/utils/open_search/` (o `src/hooks/inlabs_hook.py` do upstream o importa) nem o alias `ro_dou_src` de `runtime/runner.py`.
2. Remova o `AirflowExecutor`, o `airflow_service.py`, a variável `REGISTRALE_EXECUTOR` e os ramos do modo Airflow no painel. Mantenha `compat/airflow_shim/` (necessário para o `src/` do upstream) e a contingência sem INLABS do Sprint 6.1 (PDF integral → API do DOU, configuração `inlabs_fallback`).
3. Atualize `plano/UPSTREAM.md` com a lista final de caminhos removidos e valide `tools/sync_upstream.py` contra o `upstream/main`: o merge deve re-remover esses caminhos e os testes devem passar.
4. Limpeza do git, item a item e com confirmação: worktree `Registrale-dou-sync`, branch `upstream-sync`, stash `backup-pre-merge`, containers `sync-*` e imagens antigas, `.gitignore`. Depois integre `feature/modo-local` em `main` e crie a tag `v1.0.0`.
5. Reescreva o `README.md` (estrutura no plano), atualize o `AGENTS.md` para o estado pós-migração e corrija os manuais que citam Docker, Airflow ou `make`.

Critério principal: o `grep` do plano só encontra o que o critério de aceite permite (shim, alias `ro_dou_src`, imports do upstream em `src/`, changelog e seção de upstream); o instalador gerado a partir de `main` passa o checklist do Sprint 6; `tests/local/test_pdf_search.py` e o smoke fora do pytest passam.

Regras deste sprint:
- Faça só o escopo do Sprint 8. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Este sprint é destrutivo. Liste cada remoção (arquivos, branches, worktree, stash, containers e imagens) e **peça confirmação do usuário antes de executar**. Faça backup de `%LOCALAPPDATA%\Registrale` antes de qualquer teste final.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 8 em `plano/PLANO.md` com: o que foi feito, decisões tomadas (e por quê), arquivos criados ou alterados, comandos de validação com resultados e pendências.
2. Se tocou arquivos de `src/` ou `dag_load_inlabs/`, registre o patch em `plano/UPSTREAM.md`.
3. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
4. Peça uma revisão independente usando `plano/prompts/revisao.md`.
