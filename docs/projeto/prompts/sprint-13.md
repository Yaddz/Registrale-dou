# Prompt: Sprint 13: Acabamento visual e armazenamento dos PDFs

Você vai executar o **Sprint 13** do Registrale-DOU. Algumas telas estão tortas, cortadas ou com espaço sobrando (barra lateral recolhida, avisos, Google Sheets, template de e-mail) e a aba Armazenamento não mostra os PDFs do DOU.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro, com atenção às regras de negócio da seção 3.
2. `docs/projeto/PLANO.md`: "Decisões de arquitetura", "Pedido de 24/11/2026 (noite)" e **"Sprint 13"** (situação atual, o bloco "Atualização após o Sprint 11", tarefas e critério de aceite). O plano prevalece sobre este prompt.
3. `docs/tecnico/06_design_system.md` em toda mudança de tela.
4. Os arquivos citados (localize por texto; números de linha podem ter mudado): `templates/index.html` (barra lateral 63–135, avisos da Visão geral e de Configurações, Google Sheets ~1120–1170, template de e-mail ~1260–1440, Armazenamento ~1548), `static/css/registrale.css`, `static/js/tailwind.config.js`, `runtime/pdf_archiver.py` (`build_pdf_target_path`, layouts) e `routes/admin.py` (armazenamento).

Objetivo: todas as telas no design system, sem desalinhamentos, e os PDFs listados por mês com o espaço ocupado.

Passos:
1. Rode `git status --short` e `uv run pytest -m "not live" -q` para registrar o ponto de partida.
2. Tire as capturas "antes" (claro e escuro) das telas do critério de aceite.
3. Execute as tarefas 1 a 6 na ordem; para a tarefa 5, teste offline do endpoint nos três layouts.
4. Tire as capturas "depois" e registre a lista da passada geral.

Regras deste sprint:
- Faça só o escopo do Sprint 13. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não altere `src/`. A regra de CNPJ continua única em `src/utils/cnpj.py`.
- Menções são gravadas antes do e-mail; SMTP desligado nunca descarta menções.
- Testes usam a **rotina de teste de 16 empresas** gerada em tempo de execução a partir de `tests/fixtures/baseline/nov2026_mentions.json` (não as 122, e sem versionar nova lista de clientes). Esperado de 03 a 23/11/2026: 26 menções, 16 empresas.
- Não exiba nem versione segredos (SQLite de configurações, `.env`, credenciais do INLABS, SMTP, Google e GestãoClick) nem dados de clientes.
- Testes offline não acessam a rede.
- VM (`windows-registrale`, Podman): faça backup de `%LOCALAPPDATA%\Registrale` antes de instalar; use `dist/vm-s9/` como modelo dos scripts. Se não conseguir operar a VM, diga isso no Registro em vez de dar o item como validado.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Quando pedido, **não** adicione linhas `Co-Authored-By`. Não apague dados, containers, branches, worktrees ou stashes sem confirmação.

Ao terminar:
1. Preencha a seção **Registro** do Sprint 13 em `docs/projeto/PLANO.md` (o que foi feito, decisões, arquivos, validações com resultados e pendências).
2. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
3. Peça uma revisão independente usando `docs/projeto/prompts/revisao.md` com `<N>` = `13`.
