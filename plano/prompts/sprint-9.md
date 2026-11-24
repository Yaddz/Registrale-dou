# Prompt: Sprint 9: Pasta dos PDFs no onboarding, janela própria e ícone

Você vai executar o **Sprint 9** da migração do Registrale-DOU para aplicativo Windows. O app já roda só no modo local (o Sprint 8 removeu Docker e Airflow).

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro, com atenção às regras de negócio (seção 3) e ao upstream (seção 4).
2. `plano/PLANO.md`: "Decisões de arquitetura" e **"Sprint 9"** (situação atual, tarefas e critério de aceite). O plano prevalece sobre este prompt.
3. `rodou_dashboard/app/runtime/pdf_archiver.py`, `runtime/pdf_search.py`, `routes/admin.py` (primeiro uso e configurações), o trecho de primeiro uso de `templates/index.html`, `windows/launcher.pyw`, `windows/installer.iss`, `windows/build.ps1` e `rodou_dashboard/static/icon.svg`.

Objetivo: o analista escolhe a pasta e a organização dos PDFs no primeiro uso, o painel abre numa janela própria e o app inteiro usa o ícone do site.

Passos:
1. Rode `git status --short` e `uv run pytest -m "not live" -q` para registrar o ponto de partida.
2. Execute as tarefas 1 a 5 do Sprint 9 na ordem, com teste offline para cada comportamento novo. Comece pela tarefa 1: as outras dependem do caminho único dos PDFs.
3. Valide na VM Windows (`windows-registrale`): instalação limpa com o onboarding, atualização por cima de uma instalação com PDFs em `AAAA/MM/`, janela própria, reserva no navegador e ícones.
4. Rode a contingência PDF de novembro/2026 em cada layout (26 menções, 16 empresas).

Regras deste sprint:
- Faça só o escopo do Sprint 9. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não altere `src/`. A regra de CNPJ continua única em `src/utils/cnpj.py`.
- **Nunca mova, renomeie nem apague PDFs já salvos sem a confirmação do analista na tela**; nos testes, use pastas temporárias.
- Não use Electron. A janela é `pywebview` com WebView2 e o navegador é a reserva.
- Testes offline não acessam a rede.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 9 em `plano/PLANO.md` (o que foi feito, decisões, arquivos, validações com resultados e pendências).
2. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
3. Peça uma revisão independente usando `plano/prompts/revisao.md` com `<N>` = `9`.
