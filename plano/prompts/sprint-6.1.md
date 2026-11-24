# Prompt: Sprint 6.1: Contingência INLABS (pendências)

Você vai concluir o **Sprint 6.1: Contingência INLABS** da migração do Registrale-DOU para aplicativo Windows. O núcleo já está pronto: quando o INLABS não tem o dia, o runner busca no texto do PDF integral do DOU e confirma na API do DOU (`rodou_dashboard/app/runtime/pdf_search.py`, `runtime/runner.py::_run_inlabs_fallback`). Falta deixar isso visível e configurável para o analista.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro, com atenção à regra 6 da seção 3 (INLABS indisponível) e à seção 4 (upstream).
2. `plano/PLANO.md`: "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 6.1"** (Registro, tarefas restantes e critério de aceite). O plano prevalece sobre este prompt.
3. `rodou_dashboard/app/runtime/pdf_search.py`, `runtime/runner.py`, `runtime/pdf_archiver.py` e `tests/local/test_pdf_search.py`.

Objetivo: o analista vê qual fonte foi usada em cada busca, escolhe a fonte de contingência na tela e é avisado quando o INLABS está fora.

Passos:
1. Rode `git status --short` e `uv run pytest -m "not live and not airflow" -q` para registrar o ponto de partida.
2. Execute as **tarefas restantes 1 a 7** do Sprint 6.1 no plano, uma de cada vez, com teste offline para cada comportamento novo.
3. Rode o teste `live` do fallback (tarefa 5) para um dia da baseline e compare com `tests/fixtures/baseline/nov2026_mentions.json`.

Regras deste sprint:
- Faça só o escopo do Sprint 6.1. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Não altere `src/` nem `dag_load_inlabs/`. A regra de CNPJ continua única em `src/utils/cnpj.py`.
- Testes offline não acessam a rede: `tests/local/conftest.py` força `REGISTRALE_INLABS_FALLBACK=api`; use dados falsos para o modo `pdf`.
- Se o visualizador de `pesquisa.in.gov.br` passar a exigir captcha, **não contorne**: a busca deve cair para a API do DOU e registrar o motivo.
- O modo Docker continua funcionando; não mude o Airflow (a tarefa 7 é só documentação).
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Complete a seção **Registro** do Sprint 6.1 em `plano/PLANO.md` (o que foi feito, decisões, arquivos, validações com resultados e pendências), sem apagar o que já está registrado.
2. Demonstre cada item do **critério de aceite** com evidência. Diga claramente o que não pôde ser validado e por quê.
3. Peça uma revisão independente usando `plano/prompts/revisao.md` com `<N>` = `6.1`.
