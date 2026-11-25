# Prompt: Sprint 15: Documentação unificada e limpeza

Você vai executar o **Sprint 15** do Registrale-DOU. A documentação está espalhada e duplicada (dois `MANUAL.md`, cópias em `docs/docs/dashboard/`, `plano/` separado, MkDocs do upstream ensinando Docker/WSL/K8s) e há sobras de trabalho no repositório.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro, com atenção às regras de negócio da seção 3.
2. `docs/projeto/PLANO.md`: "Decisões de arquitetura", "Pedido de 24/11/2026 (noite)" e **"Sprint 15"** (situação atual, o bloco "Atualização após o Sprint 11", tarefas e critério de aceite). O plano prevalece sobre este prompt.
3. `docs/tecnico/06_design_system.md` em toda mudança de tela.
4. Os arquivos citados (localize por texto; números de linha podem ter mudado): `README.md`, `MANUAL.md`, `rodou_dashboard/docs/`, `docs/` (com `mkdocs.yml`), `plano/` inteiro, `AGENTS.md`, `CHANGELOG.md`, `routes/admin.py::get_user_manual`, `windows/build.ps1` e `windows/installer.iss`.

Objetivo: uma documentação só, atual e enxuta, com o plano dentro dela, e um repositório sem arquivos soltos.

Passos:
1. Rode `git status --short` e `uv run pytest -m "not live" -q` para registrar o ponto de partida.
2. Proponha no Registro a árvore final de `docs/` e a lista de arquivos soltos com a ação sugerida; **pergunte ao usuário** sobre manter ou remover o MkDocs e sobre cada remoção antes de apagar.
3. Mova com `git mv`, reescreva o manual único cobrindo os Sprints 11 a 14 e atualize todas as referências de caminho (inclusive este prompt e os demais em `prompts/`, `AGENTS.md`, build e testes).
4. Rode um script de checagem de links e o build do instalador com os novos caminhos.

Regras deste sprint:
- Faça só o escopo do Sprint 15. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não altere `src/`. A regra de CNPJ continua única em `src/utils/cnpj.py`.
- Menções são gravadas antes do e-mail; SMTP desligado nunca descarta menções.
- Testes usam a **rotina de teste de 16 empresas** gerada em tempo de execução a partir de `tests/fixtures/baseline/nov2026_mentions.json` (não as 122, e sem versionar nova lista de clientes). Esperado de 03 a 23/11/2026: 26 menções, 16 empresas.
- Não exiba nem versione segredos (SQLite de configurações, `.env`, credenciais do INLABS, SMTP, Google e GestãoClick) nem dados de clientes.
- Testes offline não acessam a rede.
- VM (`windows-registrale`, Podman): faça backup de `%LOCALAPPDATA%\Registrale` antes de instalar; use `dist/vm-s9/` como modelo dos scripts. Se não conseguir operar a VM, diga isso no Registro em vez de dar o item como validado.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Quando pedido, **não** adicione linhas `Co-Authored-By`. Não apague dados, containers, branches, worktrees ou stashes sem confirmação.

Ao terminar:
1. Preencha a seção **Registro** do Sprint 15 em `docs/projeto/PLANO.md` (o que foi feito, decisões, arquivos, validações com resultados e pendências).
2. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
3. Peça uma revisão independente usando `docs/projeto/prompts/revisao.md` com `<N>` = `15`.
