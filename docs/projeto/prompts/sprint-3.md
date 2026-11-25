# Prompt: Sprint 3: Agendador, servidor e ciclo de vida

Você vai executar o **Sprint 3: Agendador, servidor e ciclo de vida** da migração do Registrale-DOU para aplicativo Windows.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro: regras de trabalho, regras de negócio (seção 3) e compatibilidade com o upstream (seção 4).
2. `docs/projeto/PLANO.md`: seções "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 3"**. Consulte o plano sempre que tiver dúvida de escopo; ele prevalece sobre este prompt.
3. O Registro do Sprint 2 em `docs/projeto/PLANO.md`.

Objetivo: o modo local roda sozinho todo dia, num processo único, estável no Windows.

Passos principais (detalhes no plano):
1. Implemente o ponto de entrada `registrale` com waitress (1 processo), lock de instância única e inicialização do banco.
2. Implemente o APScheduler com jobstore SQLite: rotinas pelo cron do YAML, sincronização do Sheets como job (eliminando o agendamento duplicado pelos workers do gunicorn) e execução de jobs perdidos ao ligar o PC.
3. Use diretórios de dados por plataforma (`platformdirs`) e troque os caminhos fixos do container (`/data`, `/dag_confs`, `/mnt/airflow-logs`) por configuração.
4. Logs com rotação, visíveis no painel. Rotule a falha de SMTP como "Erro Envio E-mail".
5. Valide no Windows real ou numa VM (`uv run registrale`) e registre a evidência.

Regras deste sprint:
- Faça só o escopo do Sprint 3. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Os dois modos devem continuar funcionando (`REGISTRALE_EXECUTOR=airflow` e `local`). Nada pode quebrar o modo Docker atual.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 3 em `docs/projeto/PLANO.md` com: o que foi feito, decisões tomadas (e por quê), arquivos criados ou alterados, comandos de validação com resultados e pendências.
2. Se tocou arquivos de `src/` ou `dag_load_inlabs/`, registre o patch em `docs/tecnico/UPSTREAM.md`.
3. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
4. Peça uma revisão independente usando `docs/projeto/prompts/revisao.md`.
