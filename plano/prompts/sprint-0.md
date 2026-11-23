# Prompt: Sprint 0: Base e baseline

Você vai executar o **Sprint 0: Base e baseline** da migração do Registrale-DOU para aplicativo Windows.

Leitura obrigatória antes de qualquer ação:
1. `AGENTS.md`, inteiro: regras de trabalho, regras de negócio (seção 3) e compatibilidade com o upstream (seção 4).
2. `plano/PLANO.md`: seções "Decisões de arquitetura", "Baseline de paridade" e **"Sprint 0"**. Consulte o plano sempre que tiver dúvida de escopo; ele prevalece sobre este prompt.

Objetivo: congelar o estado atual que funciona e gravar a referência que o modo local terá de reproduzir.

Passos:
1. Rode `git status --short` e mostre ao usuário o que está pendente. **Peça autorização** antes de commitar e proponha commits separados por assunto (correções pós-merge, regra de CNPJ por raiz e seções, `AGENTS.md` e `plano/`).
2. Depois dos commits autorizados, proponha a tag `baseline-docker` e a branch `feature/modo-local` (também com autorização).
3. Com o modo Docker rodando, grave as fixtures descritas no plano em `tests/fixtures/baseline/`. Não grave dados pessoais além do necessário e nunca grave configurações ou segredos.
4. Escreva `plano/INVENTARIO.md` cobrindo 100% dos pontos de contato com o Airflow e o Docker (arquivo:linha, o que faz, substituto previsto e sprint).
5. Crie o `pyproject.toml` com `uv` (Python 3.11, grupos `core`/`dashboard`/`dev`, sem Airflow). Ainda não é necessário que tudo rode fora do Docker; isso é o Sprint 1.

Regras deste sprint:
- Faça só o escopo do Sprint 0. Se surgir algo de outro sprint, anote no Registro como pendência; não implemente.
- Os dois modos devem continuar funcionando (`REGISTRALE_EXECUTOR=airflow` e `local`). Nada pode quebrar o modo Docker atual.
- Não crie commits, branches, tags nem push sem pedido explícito do usuário. Não apague dados, containers, branches, worktrees ou stashes.
- Não exiba nem versione segredos (configurações do SQLite, `.env`, credenciais do INLABS, SMTP e Google).

Ao terminar:
1. Preencha a seção **Registro** do Sprint 0 em `plano/PLANO.md` com: o que foi feito, decisões tomadas (e por quê), arquivos criados ou alterados, comandos de validação com resultados e pendências.
2. Se tocou arquivos de `src/` ou `dag_load_inlabs/`, registre o patch em `plano/UPSTREAM.md`.
3. Demonstre cada item do **critério de aceite** com evidência (saída de comando, contagem, captura). Diga claramente o que não pôde ser validado e por quê.
4. Peça uma revisão independente usando `plano/prompts/revisao.md`.
