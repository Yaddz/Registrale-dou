# Prompt: Sprint 10: Ajustes de uso do painel e privacidade da rotina

Você vai executar o **Sprint 10** do Registrale-DOU. O app já é só modo local, abre em janela própria e segue o design system do painel.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro, com atenção às regras de negócio da seção 3 (em especial a regra 5: menções são gravadas antes do e-mail).
2. `plano/PLANO.md`: "Decisões de arquitetura" e **"Sprint 10"** (situação atual, tarefas e critério de aceite). O plano prevalece sobre este prompt.
3. `rodou_dashboard/docs/06_design_system.md`: use os componentes e tokens descritos ali em toda mudança de tela.
4. Os arquivos citados na situação atual: `templates/index.html` (`maskDate`, Arquivo PDF DOU, avisos da Visão geral, Integrações), `routes/dags.py` (`api_pdf_archive_run`, `api_integrations_status`), `routes/admin.py` e `routes/auth.py` ("Última sync"), `runtime/pdf_archiver.py`, `runtime/paths.py` (`_seed_routines_if_empty`), `services/email_service.py`, `windows/build.ps1`.

Objetivo: corrigir os incômodos de uso achados no Sprint 9, permitir fechar os avisos da Visão geral, desligar o e-mail sem o sistema acusar pendência e parar de distribuir a lista de clientes no instalador.

Passos:
1. Rode `git status --short` e `uv run pytest -m "not live" -q` para registrar o ponto de partida.
2. Execute as tarefas 1 a 8 do Sprint 10 na ordem, com teste offline para cada comportamento novo.
3. Valide as telas no navegador (servidor local com `REGISTRALE_DATA_DIR` temporário) e, para o instalador, na VM Windows (`windows-registrale`): instalação limpa sem os CNPJs, "Última sync: Nunca" e SMTP desligado sem pendência.
4. Rode a contingência PDF de novembro/2026 com a rotina de teste da baseline (26 menções, 16 empresas).

Regras deste sprint:
- Faça só o escopo do Sprint 10. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não altere `src/`. A regra de CNPJ continua única em `src/utils/cnpj.py`.
- SMTP desligado nunca pode descartar menções: o envio é pulado, a busca e a gravação continuam.
- **Não reescreva o histórico do git, não apague releases nem assets do GitHub** para remover a lista de clientes: só pare de versioná-la e de empacotá-la, e registre as opções para o usuário decidir.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google) nem dados de clientes em fixtures; use CNPJs sintéticos.
- Testes offline não acessam a rede.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Quando pedido, **não** adicione linhas `Co-Authored-By` nas mensagens de commit. Não apague dados, containers, branches, worktrees ou stashes.

Ao terminar:
1. Preencha a seção **Registro** do Sprint 10 em `plano/PLANO.md` (o que foi feito, decisões, arquivos, validações com resultados e pendências).
2. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
3. Peça uma revisão independente usando `plano/prompts/revisao.md` com `<N>` = `10`.
