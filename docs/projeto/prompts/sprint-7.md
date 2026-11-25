# Prompt: Sprint 7: Validação de paridade 100% e homologação

Você vai executar o **Sprint 7: Validação de paridade 100% e homologação** da migração do Registrale-DOU para aplicativo Windows.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro: regras de trabalho, regras de negócio (seção 3) e compatibilidade com o upstream (seção 4).
2. `docs/projeto/PLANO.md`: seções "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 7"**. Consulte o plano sempre que tiver dúvida de escopo; ele prevalece sobre este prompt.
3. Os Registros de todos os sprints anteriores (inclusive o **6.1**, com os achados da revisão) e `docs/tecnico/UPSTREAM.md`.

Objetivo: provar que o modo local substitui o Docker sem perda e obter a aprovação do usuário.

Passos:
1. Execute **todos** os itens do checklist do Sprint 7 no plano e registre a evidência de cada um em `docs/projeto/HOMOLOGACAO.md` (tabela item → resultado → evidência).
2. Para cada divergência local × Docker, investigue a causa e corrija ou apresente a explicação ao usuário. Divergência sem explicação é bloqueadora.
3. Os itens que dependem do tempo (5 dias úteis de agendamento e de PDFs) rodam no PC do analista; peça ao usuário as evidências.
4. **INLABS fora do ar:** a contingência sem INLABS (item 2 do checklist) é obrigatória. O teste com o INLABS real (item 3) só é feito se o portal estiver no ar; se não estiver, registre-o em `HOMOLOGACAO.md` como pendência e peça ao usuário que aceite seguir sem ele. Não espere o portal voltar.
5. Valide também **fora do pytest** (app instalado ou `uv run registrale`): defeitos de importação já passaram despercebidos pelos testes uma vez.
6. Ao final, apresente o resumo e peça ao usuário que registre o termo "Aprovado para remover Docker/Airflow" (nome e data). **Não** inicie o Sprint 8.

Regras deste sprint:
- Faça só o escopo do Sprint 7. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não implemente funcionalidades. Correções só para defeitos encontrados na validação, cada uma registrada e testada. O modo Docker continua disponível para a comparação.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 7 em `docs/projeto/PLANO.md` com: o que foi feito, decisões tomadas (e por quê), arquivos criados ou alterados, comandos de validação com resultados e pendências.
2. Se tocou arquivos de `src/` ou `dag_load_inlabs/`, registre o patch em `docs/tecnico/UPSTREAM.md`.
3. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
4. Peça uma revisão independente usando `docs/projeto/prompts/revisao.md`.
