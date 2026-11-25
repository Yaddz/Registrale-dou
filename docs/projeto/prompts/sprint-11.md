# Prompt: Sprint 11: Busca confiável e diagnóstico do INLABS ausente

Você vai executar o **Sprint 11** do Registrale-DOU. O app instalado (v1.2.0 + login opcional) não acha menções de forma confiável: o Postgres portátil não vem no instalador, o log repete `argument of type 'NoneType' is not iterable` a cada minuto e a busca do dia caiu no PDF com só 1 arquivo.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro, com atenção às regras de negócio da seção 3.
2. `docs/projeto/PLANO.md`: "Decisões de arquitetura", "Pedido de 24/11/2026 (noite)" e **"Sprint 11"** (situação atual, tarefas e critério de aceite). O plano prevalece sobre este prompt.
3. `docs/tecnico/06_design_system.md` em toda mudança de tela.
4. Os arquivos citados: `routes/admin.py` (~520-560), `services/inlabs_service.py`, `runtime/pg_portable.py`, `runtime/pdf_search.py`, `runtime/runner.py`, `runtime/executor.py`, `routes/dags.py` (`trigger_routine`, `api_trigger_monthly`, `api_integrations_status`), `services/dag_config_service.py`, `runtime/paths.py` (`_EMPTY_MAIN_ROUTINE_YAML`), `services/mention_service.py` e `tests/local/test_parity_nov2026.py`.

Objetivo: a busca diária funciona sem o Postgres portátil, o log fica limpo e a tela distingue "dia sem menções" de "busca incompleta".

Passos:
1. Rode `git status --short` e `uv run pytest -m "not live" -q` para registrar o ponto de partida.
2. Reproduza na VM com a versão atual de `main` (tarefa 1) antes de mudar código; guarde o log.
3. Execute as tarefas 2 a 9 na ordem, com teste offline para cada comportamento novo.
4. Rode a rotina de teste de 03 a 23/11/2026 pela contingência PDF e pela API e compare com a baseline.
5. Reinstale na VM com o código do sprint e valide o log e as execuções do critério de aceite.

Regras deste sprint:
- Faça só o escopo do Sprint 11. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não altere `src/`. A regra de CNPJ continua única em `src/utils/cnpj.py`.
- Menções são gravadas antes do e-mail; SMTP desligado nunca descarta menções.
- Testes usam a **rotina de teste de 16 empresas** gerada em tempo de execução a partir de `tests/fixtures/baseline/nov2026_mentions.json` (não as 122, e sem versionar nova lista de clientes). Esperado de 03 a 23/11/2026: 26 menções, 16 empresas.
- Não exiba nem versione segredos (SQLite de configurações, `.env`, credenciais do INLABS, SMTP, Google e GestãoClick) nem dados de clientes.
- Testes offline não acessam a rede.
- VM (`windows-registrale`, Podman): faça backup de `%LOCALAPPDATA%\Registrale` antes de instalar; use `dist/vm-s9/` como modelo dos scripts. Se não conseguir operar a VM, diga isso no Registro em vez de dar o item como validado.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Quando pedido, **não** adicione linhas `Co-Authored-By`. Não apague dados, containers, branches, worktrees ou stashes sem confirmação.

Ao terminar:
1. Preencha a seção **Registro** do Sprint 11 em `docs/projeto/PLANO.md` (o que foi feito, decisões, arquivos, validações com resultados e pendências).
2. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
3. Peça uma revisão independente usando `docs/projeto/prompts/revisao.md` com `<N>` = `11`.
