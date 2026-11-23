# Prompt: Sprint 6: Instalador Windows

Você vai executar o **Sprint 6: Instalador Windows** da migração do Registrale-DOU para aplicativo Windows.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro: regras de trabalho, regras de negócio (seção 3) e compatibilidade com o upstream (seção 4).
2. `plano/PLANO.md`: seções "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 6"**. Consulte o plano sempre que tiver dúvida de escopo; ele prevalece sobre este prompt.
3. Os Registros dos Sprints 3, 4 e 5 em `plano/PLANO.md`.

Objetivo: instalação de um clique e uso diário sem terminal no Windows 10/11.

Passos principais (detalhes no plano):
1. `windows/build.ps1`: Python 3.11 embeddable com hash verificado, dependências travadas, app e PostgreSQL portátil → Inno Setup (`windows/installer.iss`).
2. `windows/launcher.pyw`: ícone na bandeja (Abrir, Status, Logs, Reiniciar, Sair), sem console, atalhos e início automático opcional.
3. Assistente de primeira execução que importa `database.db` e as rotinas atuais, com backup antes.
4. Atualização pelas Releases do GitHub (com verificação de SHA-256), migrações versionadas e dados preservados. A desinstalação mantém os dados por padrão.
5. Workflow `windows-build.yml` que testa, empacota e publica o artefato. **Não** publique release sem pedido do usuário.

Valide numa VM Windows limpa e registre cada passo do critério de aceite.

Regras deste sprint:
- Faça só o escopo do Sprint 6. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Os dois modos devem continuar funcionando (`REGISTRALE_EXECUTOR=airflow` e `local`). Nada pode quebrar o modo Docker atual.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 6 em `plano/PLANO.md` com: o que foi feito, decisões tomadas (e por quê), arquivos criados ou alterados, comandos de validação com resultados e pendências.
2. Se tocou arquivos de `src/` ou `dag_load_inlabs/`, registre o patch em `plano/UPSTREAM.md`.
3. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
4. Peça uma revisão independente usando `plano/prompts/revisao.md`.
