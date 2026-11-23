# Prompt: Sprint 1: Núcleo sem Airflow e procedimento de upstream

Você vai executar o **Sprint 1: Núcleo sem Airflow e procedimento de upstream** da migração do Registrale-DOU para aplicativo Windows.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro: regras de trabalho, regras de negócio (seção 3) e compatibilidade com o upstream (seção 4).
2. `plano/PLANO.md`: seções "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 1"**. Consulte o plano sempre que tiver dúvida de escopo; ele prevalece sobre este prompt.
3. `plano/INVENTARIO.md` (lista de símbolos `airflow.*` usados por `src/`).

Objetivo: `src/` importa e executa num Python comum, sem Airflow instalado e **sem editar os arquivos do upstream**.

Passos principais (detalhes no plano):
1. Implemente `compat/airflow_shim/` com só os símbolos realmente usados, cada um coberto por teste. O que o modo local não usa deve falhar com `NotImplementedError` explicativo.
2. Implemente `compat/bootstrap.py::install_airflow_shim()`, ativado só quando o Airflow real não estiver instalado.
3. Crie `tests/local/test_shim_imports.py` e marque com `@pytest.mark.airflow` os testes que exigem Airflow real.
4. Escreva `plano/UPSTREAM.md` (procedimento, patches locais existentes e caminhos removidos) e `tools/sync_upstream.py`. Faça o ensaio do sync numa branch descartável e **não** altere `main`.
5. Registre os comandos do modo local na seção 6 do `AGENTS.md`.

Ponto de atenção: confirme com `git diff baseline-docker -- src/` que este sprint não alterou `src/`. Se for inevitável, justifique e registre o patch.

Regras deste sprint:
- Faça só o escopo do Sprint 1. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Os dois modos devem continuar funcionando (`REGISTRALE_EXECUTOR=airflow` e `local`). Nada pode quebrar o modo Docker atual.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 1 em `plano/PLANO.md` com: o que foi feito, decisões tomadas (e por quê), arquivos criados ou alterados, comandos de validação com resultados e pendências.
2. Se tocou arquivos de `src/` ou `dag_load_inlabs/`, registre o patch em `plano/UPSTREAM.md`.
3. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
4. Peça uma revisão independente usando `plano/prompts/revisao.md`.
