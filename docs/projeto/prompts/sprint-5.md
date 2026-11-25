# Prompt: Sprint 5: Arquivo do PDF integral do DOU

Você vai executar o **Sprint 5: Arquivo do PDF integral do DOU** da migração do Registrale-DOU para aplicativo Windows.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro: regras de trabalho, regras de negócio (seção 3) e compatibilidade com o upstream (seção 4).
2. `docs/projeto/PLANO.md`: seções "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 5"**. Consulte o plano sempre que tiver dúvida de escopo; ele prevalece sobre este prompt.
3. A seção Backlog de `docs/projeto/PLANO.md` (a exportação da página destacada está em standby; não implemente).

Objetivo: guardar automaticamente o PDF integral do DOU de cada dia numa pasta local, como o analista faz hoje à mão.

Passos principais (detalhes no plano):
1. Comece pela investigação, com tempo limitado: identifique a fonte oficial do PDF integral por seção e dia e uma fonte alternativa. Registre URLs, autenticação, tamanhos e limitações **antes** de implementar.
2. Implemente `runtime/pdf_archiver.py`: idempotente, valida `%PDF` e tamanho, tenta de novo quando o portal falha e salva em `<pasta>\AAAA\MM\DOU_AAAA-MM-DD_SecaoN.pdf`.
3. Agende junto da busca diária e permita disparo manual por data ou mês.
4. Inclua configuração no painel (pasta, seções, ligar/desligar, status) e o vínculo menção → PDF do dia.

Valide num dia útil real e compare com o arquivo que o analista baixa hoje.

Regras deste sprint:
- Faça só o escopo do Sprint 5. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Os dois modos devem continuar funcionando (`REGISTRALE_EXECUTOR=airflow` e `local`). Nada pode quebrar o modo Docker atual.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 5 em `docs/projeto/PLANO.md` com: o que foi feito, decisões tomadas (e por quê), arquivos criados ou alterados, comandos de validação com resultados e pendências.
2. Se tocou arquivos de `src/` ou `dag_load_inlabs/`, registre o patch em `docs/tecnico/UPSTREAM.md`.
3. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
4. Peça uma revisão independente usando `docs/projeto/prompts/revisao.md`.
