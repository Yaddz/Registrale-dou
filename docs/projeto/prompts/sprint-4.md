# Prompt: Sprint 4: INLABS local

Você vai executar o **Sprint 4: INLABS local** da migração do Registrale-DOU para aplicativo Windows.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro: regras de trabalho, regras de negócio (seção 3) e compatibilidade com o upstream (seção 4).
2. `docs/projeto/PLANO.md`: seções "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 4"**. Consulte o plano sempre que tiver dúvida de escopo; ele prevalece sobre este prompt.
3. `dag_load_inlabs/ro_dou_inlabs_load_pg_dag.py` e `src/hooks/inlabs_hook_sql_mode.py`, inteiros.

Objetivo: baixar e pesquisar o INLABS sem Docker, mantendo o modo SQL do upstream sem alteração.

Passos principais (detalhes no plano):
1. Implemente `runtime/pg_portable.py` (PostgreSQL 17 portátil: initdb, start/stop junto com o app, só `127.0.0.1`, porta livre, schema `dou_inlabs` e `unaccent`).
2. Implemente `runtime/inlabs_loader.py` portando, não reescrevendo, as tarefas da DAG de carga, com extração ZIP segura (Zip Slip e limites) e retenção de 120 dias.
3. Faça o shim servir as conexões `inlabs_portal` e `inlabs_db` a partir das configurações do painel.
4. Integre ao executor e ao agendador (06:59 e 23:59) e à busca mensal "baixar e pesquisar".

Atenção: o portal INLABS pode estar em "Manutenção Programada" (responde HTTP 200 com essa página). Nesse caso, cumpra o critério com testes sintéticos, registre a validação real como pendente para o Sprint 7 e garanta que o fallback para a API do DOU continua funcionando.

Regras deste sprint:
- Faça só o escopo do Sprint 4. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Os dois modos devem continuar funcionando (`REGISTRALE_EXECUTOR=airflow` e `local`). Nada pode quebrar o modo Docker atual.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 4 em `docs/projeto/PLANO.md` com: o que foi feito, decisões tomadas (e por quê), arquivos criados ou alterados, comandos de validação com resultados e pendências.
2. Se tocou arquivos de `src/` ou `dag_load_inlabs/`, registre o patch em `docs/tecnico/UPSTREAM.md`.
3. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
4. Peça uma revisão independente usando `docs/projeto/prompts/revisao.md`.
