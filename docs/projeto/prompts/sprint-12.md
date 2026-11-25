# Prompt: Sprint 12: Estado das configurações, SMTP desligado e atividade visível

Você vai executar o **Sprint 12** do Registrale-DOU. Os interruptores do painel seguem dois modelos e alguns não gravam o estado; o assistente acusa como pendência o que foi pausado; com o SMTP desligado as rotinas ainda exigem e-mail; o analista não vê o que está rodando nem consegue atualizar a tela.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro, com atenção às regras de negócio da seção 3.
2. `docs/projeto/PLANO.md`: "Decisões de arquitetura", "Pedido de 24/11/2026 (noite)" e **"Sprint 12"** (situação atual, o bloco "Atualização após o Sprint 11", tarefas e critério de aceite). O plano prevalece sobre este prompt.
3. `docs/tecnico/06_design_system.md` em toda mudança de tela.
4. Os arquivos citados (localize por texto; números de linha podem ter mudado): `templates/index.html` (interruptores listados na situação atual, assistente de integrações, aviso de pendências, verificação de atualização ~3700), `routes/dags.py` (validações de e-mail ~200 e ~448, `api_integrations_status`), `routes/admin.py` (configurações, caches), `services/email_service.py`, `services/inlabs_service.py` (caches), `runtime/scheduler.py`, `runtime/executor.py` e `windows/launcher.pyw` (menu da bandeja).

Objetivo: um só modelo de interruptor gravando o estado, desativado ≠ pendente, e-mail desligado em todo o app e atividade sempre visível.

Passos:
1. Rode `git status --short` e `uv run pytest -m "not live" -q` para registrar o ponto de partida.
2. Faça o inventário de todos os interruptores e checkboxes de ativação do painel (tela, chave, quando grava) e registre antes de mudar.
3. Execute as tarefas 1 a 6 na ordem, com teste offline para cada comportamento novo.
4. Valide no navegador (servidor local com `REGISTRALE_DATA_DIR` temporário) os cenários do critério de aceite, recarregando a página e reiniciando o servidor.

Regras deste sprint:
- Faça só o escopo do Sprint 12. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não altere `src/`. A regra de CNPJ continua única em `src/utils/cnpj.py`.
- Menções são gravadas antes do e-mail; SMTP desligado nunca descarta menções.
- Testes usam a **rotina de teste de 16 empresas** gerada em tempo de execução a partir de `tests/fixtures/baseline/nov2026_mentions.json` (não as 122, e sem versionar nova lista de clientes). Esperado de 03 a 23/11/2026: 26 menções, 16 empresas.
- Não exiba nem versione segredos (SQLite de configurações, `.env`, credenciais do INLABS, SMTP, Google e GestãoClick) nem dados de clientes.
- Testes offline não acessam a rede.
- VM (`windows-registrale`, Podman): faça backup de `%LOCALAPPDATA%\Registrale` antes de instalar; use `dist/vm-s9/` como modelo dos scripts. Se não conseguir operar a VM, diga isso no Registro em vez de dar o item como validado.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Quando pedido, **não** adicione linhas `Co-Authored-By`. Não apague dados, containers, branches, worktrees ou stashes sem confirmação.

Ao terminar:
1. Preencha a seção **Registro** do Sprint 12 em `docs/projeto/PLANO.md` (o que foi feito, decisões, arquivos, validações com resultados e pendências).
2. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
3. Peça uma revisão independente usando `docs/projeto/prompts/revisao.md` com `<N>` = `12`.
