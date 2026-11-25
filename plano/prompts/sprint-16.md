# Prompt: Sprint 16: Homologação na VM e release 1.3.0

Você vai executar o **Sprint 16** do Registrale-DOU. Os Sprints 11 a 15 estão aprovados; falta validar o pacote final no Windows como o analista vai usar e publicar a versão.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro, com atenção às regras de negócio da seção 3.
2. `plano/PLANO.md`: "Decisões de arquitetura", "Pedido de 24/11/2026 (noite)" e **"Sprint 16"** (situação atual, o bloco "Atualização após o Sprint 11", tarefas e critério de aceite). O plano prevalece sobre este prompt.
3. `rodou_dashboard/docs/06_design_system.md` em toda mudança de tela.
4. Os arquivos citados (localize por texto; números de linha podem ter mudado): a seção do Sprint 16 e os Registros dos Sprints 11 a 15, `windows/build.ps1`, `windows/installer.iss`, `dist/vm-s9/` (scripts modelo) e o manual.

Objetivo: o instalador 1.3.0 validado por atualização e por instalação limpa, com evidências.

Passos:
1. Rode `git status --short` e `uv run pytest -m "not live" -q` para registrar o ponto de partida.
2. Suba a VM, instale a 1.2.0 com dados de teste e faça a atualização para a 1.3.0 (tarefa 2).
3. Faça a instalação limpa e o checklist (tarefas 3 e 4), guardando capturas, log e SHA-256.
4. Atualize a versão e o CHANGELOG; commit, tag, push e release **só com pedido do usuário**.

Regras deste sprint:
- Faça só o escopo do Sprint 16. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não altere `src/`. A regra de CNPJ continua única em `src/utils/cnpj.py`.
- Menções são gravadas antes do e-mail; SMTP desligado nunca descarta menções.
- Testes usam a **rotina de teste de 16 empresas** gerada em tempo de execução a partir de `tests/fixtures/baseline/nov2026_mentions.json` (não as 122, e sem versionar nova lista de clientes). Esperado de 03 a 23/11/2026: 26 menções, 16 empresas.
- Não exiba nem versione segredos (SQLite de configurações, `.env`, credenciais do INLABS, SMTP, Google e GestãoClick) nem dados de clientes.
- Testes offline não acessam a rede.
- VM (`windows-registrale`, Podman): faça backup de `%LOCALAPPDATA%\Registrale` antes de instalar; use `dist/vm-s9/` como modelo dos scripts. Se não conseguir operar a VM, diga isso no Registro em vez de dar o item como validado.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Quando pedido, **não** adicione linhas `Co-Authored-By`. Não apague dados, containers, branches, worktrees ou stashes sem confirmação.

Ao terminar:
1. Preencha a seção **Registro** do Sprint 16 em `plano/PLANO.md` (o que foi feito, decisões, arquivos, validações com resultados e pendências).
2. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
3. Peça uma revisão independente usando `plano/prompts/revisao.md` com `<N>` = `16`.
