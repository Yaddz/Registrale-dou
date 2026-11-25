# Hotfix — buscas diária e mensal sem nenhum resultado

> Prompt de execução para um agente (Sonnet). Leia `AGENTS.md` antes de começar.
> Trabalhe **somente** neste hotfix. Não crie commits, branches nem push.

## Contexto (diagnóstico já feito, não precisa refazer)

O app instalado (`%LOCALAPPDATA%\Programs\Registrale`, dados em `%LOCALAPPDATA%\Registrale`)
tem 122 empresas ativas e roda a rotina `Pesquisa_cnpj.yaml`, mas a busca diária e a mensal
gravam **0 menções**. Há dois defeitos independentes.

### Defeito 1 — busca mensal não executa nenhum dia (bug de código)

`rodou_dashboard/app/routes/dags.py::api_trigger_monthly` roda
`run_monthly_search_in_background` numa `threading.Thread`. Dentro dela, `_dispatch_routine(...)`
é chamado **fora** de `with app_context:` na FASE 1 (≈ linha 1856) e na FASE 2 (≈ linha 1947).

`_dispatch_routine` → `get_executor().trigger(...)` → `LocalExecutor._resolve_app()` usa
`flask.current_app` quando o singleton foi criado sem `app` (o que acontece quando a primeira
chamada a `get_executor()` vem de uma requisição HTTP; o `get_executor(app)` do agendador só roda
quando um job agendado dispara). Na thread de fundo isso levanta
`RuntimeError: Working outside of application context`, que `_dispatch_routine` engole e devolve
`ok=False`. O loop ignora o `msg`, nenhum run é criado e a FASE 3 consolida 0 menções.

Evidência no histórico do app (tabela `sync_history`):
`Busca Mensal (PDF integral + API do DOU) — Disparando ... para 16 dia(s)` e
`Busca Mensal Concluída — Nenhuma menção` **no mesmo segundo**, e não existe nenhum log
`logs/runs/local__temp_monthly_dou_*`. Reproduzido isoladamente: chamar `_dispatch_routine`
com `yaml_dict` fora de um app context devolve exatamente esse erro; dentro dele, funciona.

### Defeito 2 — filtro de órgão "ANVISA" descarta todas as publicações (config + UX)

`main_dag_settings` (SQLite, tabela `settings`) está com
`organs/department = ["ANVISA"]` e `sections = ["SECAO_1"]`, e `rebuild_yaml_from_db()` reaplica
isso no YAML a cada sincronização. O núcleo (`src/searchers.py::DOUSearcher._match_department`,
linha ≈437) mantém só resultados em que o texto do filtro é **igual a um elemento** de
`hierarchyList` (ex.: `"Agência Nacional de Vigilância Sanitária"`). A sigla "ANVISA" nunca é um
elemento, então todo resultado da API é removido. A própria tela sugere "Ex: Ministério da Saúde,
ANVISA" (`templates/index.html` ≈ linha 2623), induzindo ao erro.

`src/` é upstream — **não altere `src/searchers.py`**. A correção fica no painel.

## Tarefas

### T1. Corrigir a busca mensal (`routes/dags.py`)
1. Em `run_monthly_search_in_background`, envolva toda chamada a `_dispatch_routine(...)` em
   `with app_context:` (FASE 1 e FASE 2). Alternativa equivalente e mais robusta: fazer
   `_dispatch_routine` aceitar um `app` opcional, ou garantir que o singleton tenha `app` —
   ex.: em `create_app()`/`server.py` chamar `get_executor(app)` logo após criar o app, para que
   `_resolve_app()` nunca dependa de `current_app`. **Faça as duas coisas**: o `with app_context`
   no loop e o `get_executor(app)` na inicialização (em `rodou_dashboard/app/runtime/server.py`
   logo após `app = create_app()`, e onde mais o app for montado para o painel).
2. Quando `ok` for `False`, registre `logging.error` com o `msg` e conte as falhas; se todos os
   disparos de uma fase falharem, grave `add_history_event("Erro (Busca Mensal)", ...)` com o
   motivo, em vez de terminar como "Nenhuma menção encontrada".
3. Revise os outros `threading.Thread` de `routes/dags.py` que chamam `_dispatch_routine` ou
   `get_executor()` e confirme que todos estão dentro de app context (o ad-hoc em ≈1191 já está).

### T2. Fazer o filtro de órgão funcionar com sigla (`dag_config_service.py` / `routes/dags.py`)
1. Crie em `rodou_dashboard/app/services/organ_aliases.py` uma função
   `expand_organ_filters(orgs: list[str]) -> list[str]` que:
   - remove vazios e espaços;
   - mapeia siglas comuns (case-insensitive) para o nome oficial como aparece em `hierarchyList`
     do DOU. No mínimo: ANVISA → "Agência Nacional de Vigilância Sanitária",
     MS → "Ministério da Saúde", INPI → "Instituto Nacional da Propriedade Industrial",
     MAPA → "Ministério da Agricultura e Pecuária", INMETRO → "Instituto Nacional de Metrologia,
     Qualidade e Tecnologia", ANP, ANATEL, ANS, ANEEL, ANTT, IBAMA, CADE, RFB/Receita →
     "Secretaria Especial da Receita Federal do Brasil". Confira a grafia de pelo menos ANVISA,
     Ministério da Saúde e INPI com uma chamada real (passo T5) antes de fechar o mapa;
   - mantém nomes que não são sigla conhecida como vieram;
   - remove duplicatas preservando a ordem.
2. Aplique `expand_organ_filters` em **todo** ponto que grava `department` no YAML:
   `rebuild_yaml_from_db()` (variável `organs_val`), o salvamento de rotina em `routes/dags.py`
   (≈ linhas 346–347) e o salvamento de `main_dag_settings` (≈ linha 671). Guarde no SQLite o que o
   usuário digitou (para a tela mostrar "ANVISA"), mas grave no YAML a forma expandida.
3. Na tela (`templates/index.html` ≈ 2623 e o texto de ajuda ≈ 3277), troque o exemplo para o
   nome oficial e acrescente uma linha: "Use o nome do órgão como aparece no DOU; siglas comuns
   (ANVISA, INPI…) são convertidas automaticamente. Deixe vazio para buscar em todos os órgãos."

### T3. Corrigir a configuração do usuário instalado
Depois de T1 e T2 implementados e testados:
1. Faça backup: copie `%LOCALAPPDATA%\Registrale\database.db` para
   `database.db.bak-hotfix-<AAAAMMDDHHMM>` na mesma pasta.
2. **Não** mude a escolha do usuário de filtrar a ANVISA nem a Seção 1: com T2 o filtro passa a
   funcionar. Apenas reconstrua o YAML (rodar `rebuild_yaml_from_db()` dentro de um app context
   apontando para os dados reais, ou salvar a rotina pelo painel) e confirme que
   `rotinas/Pesquisa_cnpj.yaml` ficou com `department: ['Agência Nacional de Vigilância Sanitária']`.
3. Aplique o código corrigido ao app instalado: copie os arquivos alterados de
   `rodou_dashboard/` para `%LOCALAPPDATA%\Programs\Registrale\app\rodou_dashboard\` (mesmos
   caminhos relativos; **nunca** copie nada para `src/` do app além do que você alterou — você não
   deve alterar `src/`). Apague os `__pycache__` correspondentes.
4. Reinicie o app: encerre os processos `pythonw.exe`/`python.exe` cujo caminho está em
   `%LOCALAPPDATA%\Programs\Registrale` (use `Get-Process | Where-Object Path -like ...`), apague
   `registrale.lock` se sobrar, e reabra com o atalho da Área de Trabalho ou
   `%LOCALAPPDATA%\Programs\Registrale\python\pythonw.exe` + o launcher em `app\windows\launcher.pyw`
   (confira o comando exato no atalho `Startup\Registrale-DOU.lnk`). Confirme
   `http://127.0.0.1:5000` respondendo.

### T4. Testes (offline, sem rede)
- `rodou_dashboard/tests/test_monthly_dispatch.py`: dispara `api_trigger_monthly` (ou a função de
  fundo) com executor/`_dispatch_routine` mockados e um executor **sem** `app` vinculado; afirma que
  cada dia útil gerou um disparo bem-sucedido e que uma falha de disparo vira evento
  "Erro (Busca Mensal)". Esse teste deve falhar no código antigo.
- `rodou_dashboard/tests/test_organ_aliases.py`: sigla → nome; case-insensitive; nome desconhecido
  preservado; vazios removidos; sem duplicata; `rebuild_yaml_from_db` grava a forma expandida.
- Rode `uv run pytest -m "not live"` (se `uv` não existir na máquina, instale com
  `pip install uv` no Python do usuário ou rode `python -m pytest` com o Python embutido do app:
  `%LOCALAPPDATA%\Programs\Registrale\python\python.exe -m pytest`). Registre o resultado.

### T5. Validação real (rede)
Com o app reiniciado:
1. Rode, pelo painel ou por script com app context, a rotina principal para **24/11/2026** e
   **18/11/2026** e anote quantas menções saíram.
2. Rode a busca mensal de **11/2026** pelo painel. Confirme no histórico que apareceram runs
   `local__temp_monthly_dou_*` em `logs/runs/` (um por dia útil, 16 no total) e que a FASE 3
   contou as menções. Isso demora (≈3 min por dia); rode em segundo plano e espere terminar.
3. Se mesmo assim der 0, rode a mesma data com `department: []` e as 4 seções num YAML temporário
   e compare: se aparecerem resultados da ANVISA, o mapa de T2 está com grafia errada.

### T6. Documentação
- Acrescente uma seção "Hotfix — buscas sem resultado" no final de `docs/projeto/PLANO.md` com
  causa, correção, comandos e resultados de T4/T5.
- Entrada em `CHANGELOG.md` (versão de patch, ex.: 1.3.1) e, se mudar `VERSION`/`version.py`,
  mantenha os dois coerentes.

## Critério de aceite
- Busca mensal de 11/2026 cria um run por dia útil e termina com o número real de menções.
- Busca diária com filtro "ANVISA" retorna as publicações da ANVISA que citam os CNPJs.
- Nenhuma alteração em `src/`.
- `pytest -m "not live"` passa sem regressões.
- Relatório final: arquivos alterados, comandos executados, resultados, o que não foi validado.
