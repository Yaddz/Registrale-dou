# Prompt: Revisão independente de sprint

Você vai revisar o trabalho do **Sprint <N>** do Registrale-DOU. Trabalhe em **modo somente leitura**: não corrija código, entregue os achados.

Leitura obrigatória:
1. `AGENTS.md`, com atenção à seção 3 (regras de negócio que não podem regredir), à seção 4 (compatibilidade com o upstream) e ao papel "Revisão".
2. `plano/PLANO.md`: a seção do **Sprint <N>** (tarefas, critério de aceite) e o Registro preenchido pelo executor.
3. `git status --short` e o diff do sprint. Revise só o código novo ou afetado; não atribua ao autor mudanças preexistentes.

Verifique:
- Cada item do critério de aceite foi cumprido **com evidência reproduzível**? Rode você mesmo os testes indicados no Registro.
- Regressões nas regras de negócio: CNPJ por raiz, seções, menções gravadas antes do e-mail, fallback do INLABS, datas e baseline de novembro/2026 (26 menções, 16 empresas).
- Enquanto existirem os dois modos: o modo Docker (`REGISTRALE_EXECUTOR=airflow`) continua funcionando?
- Compatibilidade com o upstream: houve mudança em `src/` ou `dag_load_inlabs/`? Está registrada em `plano/UPSTREAM.md` e é mínima?
- Windows: caminhos, encoding, processos, portas, permissões e ausência de dependências só de Linux.
- Concorrência e idempotência (agendador, threads, buscas repetidas e downloads), timeouts e retries, uso de memória e rede.
- Segurança: segredos em log, diff ou navegador; path traversal; Zip Slip; HTML do DOU sem escape; downloads sem verificação.
- Testes cobrem o comportamento novo e os caminhos de erro, de forma determinística e sem rede (exceto `live`).

Formato da resposta:
1. **Bloqueadores** (impedem aceitar o sprint), depois **Importantes** e **Sugestões**. Cada achado com arquivo:linha, cenário concreto, impacto e correção recomendada.
2. Validações que você executou e seus resultados.
3. Veredito: "Sprint <N> aprovado" ou "Sprint <N> reprovado", com a lista do que falta. Não aprove com bloqueador em aberto.
