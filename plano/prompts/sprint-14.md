# Prompt: Sprint 14: Onboarding completo

Você vai executar o **Sprint 14** do Registrale-DOU. O primeiro uso só cobre importação, pasta dos PDFs e login; rotina, empresas, GestãoClick, SMTP e INLABS ficam para o analista descobrir em Configurações.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro, com atenção às regras de negócio da seção 3.
2. `plano/PLANO.md`: "Decisões de arquitetura", "Pedido de 24/11/2026 (noite)" e **"Sprint 14"** (situação atual, o bloco "Atualização após o Sprint 11", tarefas e critério de aceite). O plano prevalece sobre este prompt.
3. `rodou_dashboard/docs/06_design_system.md` em toda mudança de tela.
4. Os arquivos citados (localize por texto; números de linha podem ter mudado): `templates/index.html` (primeiro uso, `pdfOnboarding`, `needs_access_onboarding`, formulários de Configurações), `routes/admin.py` (`first_run_status`, `first_run_import`, configurações), `routes/dags.py` (rotina principal, integrações), `services/sheets_service.py`, o serviço do GestãoClick e `services/email_service.py`.

Objetivo: o analista termina o primeiro uso com o app pronto para a busca das 8h, ou com cada integração conscientemente desativada.

Passos:
1. Rode `git status --short` e `uv run pytest -m "not live" -q` para registrar o ponto de partida.
2. Desenhe os 9 passos reaproveitando os formulários e endpoints de Configurações (sem lógica duplicada) e os estados do Sprint 12.
3. Execute as tarefas 1 a 5, com testes offline dos endpoints de estado do assistente.
4. Valide no navegador com `REGISTRALE_DATA_DIR` limpo (caminho completo, caminho pulando tudo e retomada) e, por fim, numa instalação limpa na VM.

Regras deste sprint:
- Faça só o escopo do Sprint 14. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não altere `src/`. A regra de CNPJ continua única em `src/utils/cnpj.py`.
- Menções são gravadas antes do e-mail; SMTP desligado nunca descarta menções.
- Testes usam a **rotina de teste de 16 empresas** gerada em tempo de execução a partir de `tests/fixtures/baseline/nov2026_mentions.json` (não as 122, e sem versionar nova lista de clientes). Esperado de 03 a 23/11/2026: 26 menções, 16 empresas.
- Não exiba nem versione segredos (SQLite de configurações, `.env`, credenciais do INLABS, SMTP, Google e GestãoClick) nem dados de clientes.
- Testes offline não acessam a rede.
- VM (`windows-registrale`, Podman): faça backup de `%LOCALAPPDATA%\Registrale` antes de instalar; use `dist/vm-s9/` como modelo dos scripts. Se não conseguir operar a VM, diga isso no Registro em vez de dar o item como validado.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Quando pedido, **não** adicione linhas `Co-Authored-By`. Não apague dados, containers, branches, worktrees ou stashes sem confirmação.

Ao terminar:
1. Preencha a seção **Registro** do Sprint 14 em `plano/PLANO.md` (o que foi feito, decisões, arquivos, validações com resultados e pendências).
2. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
3. Peça uma revisão independente usando `plano/prompts/revisao.md` com `<N>` = `14`.
