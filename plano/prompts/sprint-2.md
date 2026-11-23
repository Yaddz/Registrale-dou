# Prompt: Sprint 2: Executor local (busca DOU) e camada de executor no painel

Você vai executar o **Sprint 2: Executor local (busca DOU) e camada de executor no painel** da migração do Registrale-DOU para aplicativo Windows.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro: regras de trabalho, regras de negócio (seção 3) e compatibilidade com o upstream (seção 4).
2. `plano/PLANO.md`: seções "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 2"**. Consulte o plano sempre que tiver dúvida de escopo; ele prevalece sobre este prompt.
3. `plano/INVENTARIO.md` e as fixtures em `tests/fixtures/baseline/`.

Objetivo: o painel executa as rotinas sem o Airflow e reproduz exatamente as menções da baseline.

Passos principais (detalhes no plano):
1. Implemente `rodou_dashboard/app/runtime/runner.py` reproduzindo os argumentos que `dou_dag_generator.perform_searches` passa aos buscadores. O retorno deve ser idêntico ao XCom de `exec_search_N` (compare com `run_result_*.json`).
2. Implemente a interface `Executor` (`AirflowExecutor` encapsulando o código atual e `LocalExecutor` com threads e a tabela `job_runs`).
3. Migre para a interface **todas** as chamadas ao Airflow do inventário. As "DAGs temporárias" (mensal e avulsa) viram execuções em memória, sem arquivos em `dag_confs/`.
4. Testes offline com as fixtures, mais o teste de paridade `live` de novembro/2026.

Critério principal: no modo local, novembro/2026 gera **26 menções de 16 empresas**, iguais às da fixture (CNPJ, data e link). Mostre a comparação.

Regras deste sprint:
- Faça só o escopo do Sprint 2. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Os dois modos devem continuar funcionando (`REGISTRALE_EXECUTOR=airflow` e `local`). Nada pode quebrar o modo Docker atual.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 2 em `plano/PLANO.md` com: o que foi feito, decisões tomadas (e por quê), arquivos criados ou alterados, comandos de validação com resultados e pendências.
2. Se tocou arquivos de `src/` ou `dag_load_inlabs/`, registre o patch em `plano/UPSTREAM.md`.
3. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
4. Peça uma revisão independente usando `plano/prompts/revisao.md`.
