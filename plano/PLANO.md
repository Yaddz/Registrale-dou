# Plano de migração: Registrale-DOU para aplicativo Windows

Fonte da verdade da migração. Cada sprint tem objetivo, escopo, tarefas, entregáveis, critério de aceite e uma seção **Registro**, que o agente executor preenche ao terminar. Regras de trabalho em [`../AGENTS.md`](../AGENTS.md); prompts prontos em [`prompts/`](prompts/).

## Decisões de arquitetura

| Tema | Decisão | Motivo |
|---|---|---|
| Execução | Executor local dentro do painel, sem Airflow | Um analista só; Airflow + Docker usam ~2 GB de RAM e exigem WSL/Docker Desktop (licença paga em empresas grandes) |
| Núcleo de busca | `src/` do upstream intacto, rodando sobre `compat/airflow_shim/` | Continuar recebendo atualizações do Ro-DOU oficial com conflitos mínimos |
| Agendamento | APScheduler num único processo | Substitui o scheduler do Airflow e corrige o agendador do Sheets duplicado pelos 2 workers do gunicorn |
| Servidor web | waitress (1 processo, várias threads) | gunicorn não roda no Windows |
| Dados do painel | SQLite (`database.db`), como hoje | Já é o banco do painel |
| Dados INLABS | PostgreSQL **portátil** gerido pelo app (binários embutidos, porta local, sem serviço do Windows) | Mantém o modo SQL do upstream (`~*`, `unaccent`) sem tradução; atualizações do upstream continuam valendo |
| Empacotamento | Python 3.11 *embeddable* + dependências + Inno Setup → `Registrale-Setup-x.y.z.exe` | Menos falso positivo de antivírus que PyInstaller e fácil de inspecionar e corrigir |
| Execução no Windows | Launcher na bandeja do sistema (pystray), início automático com o Windows, abre `http://localhost:5000` | O analista não precisa abrir terminal |
| Diretórios | Programa em `%LOCALAPPDATA%\Programs\Registrale`; dados em `%LOCALAPPDATA%\Registrale`; PDFs em `Documentos\Registrale\DOU` (configurável) | Atualizar ou reinstalar não apaga dados |
| Transição | `REGISTRALE_EXECUTOR=airflow\|local`; o modo Docker segue funcionando até o Sprint 8 | Permite comparar os dois modos lado a lado |
| Atualização do app | Verificação de nova versão nas Releases do GitHub + instalador com hash SHA-256 | Simples e auditável |
| Upstream | Merge periódico de `upstream/main` com script que reaplica as remoções e roda os testes | Requisito do projeto |

## Baseline de paridade

Gerada no Sprint 0 e usada nos Sprints 2 e 7:

- Rotina `Pesquisa_cnpj.yaml` (122 CNPJs, Seções 1/2/3 + Extras), novembro/2026 (03–23/11, 14 dias úteis; 20/11 é feriado), via API do DOU → **26 menções, 16 empresas**.
- Execuções de dia único: 19/11/2026 → 0 menções das 122 empresas; 03/11 e 23/11 → incluem SURGITEC só pela raiz (`24.684.423`).

## Visão geral

| Sprint | Entrega | Depende de |
|---|---|---|
| 0 | Base congelada, baseline gravada, ambiente de desenvolvimento local | — |
| 1 | Núcleo `src/` rodando sem Airflow (shim) + procedimento de upstream | 0 |
| 2 | Executor local da busca DOU + camada de executor no painel | 1 |
| 3 | Agendador, servidor waitress, ciclo de vida e logs | 2 |
| 4 | INLABS local (PostgreSQL portátil + carga) | 2 (pode correr em paralelo ao 3) |
| 5 | Arquivo automático do PDF integral do DOU | 3 |
| 6 | Instalador Windows, launcher, migração de dados e atualização | 3, 4, 5 |
| 7 | Validação de paridade 100% e homologação com o analista | 6 |
| 8 | Remoção de Docker/Airflow, limpeza do git, novo README | Aprovação escrita do Sprint 7 |
| Backlog | Exportar a página com a menção destacada (standby) | 5 |

---

## Sprint 0: Base e baseline

**Objetivo:** congelar o estado atual que funciona e gravar a referência contra a qual o modo local será comparado.

**Tarefas**
1. Com autorização do usuário, commitar o trabalho pendente em `main` (correções pós-merge, regra de CNPJ por raiz, seções, `AGENTS.md`, `plano/`), em commits separados por assunto.
2. Criar a tag `baseline-docker` e a branch `feature/modo-local`.
3. Gravar fixtures de paridade a partir do modo Docker:
   - `tests/fixtures/baseline/nov2026_mentions.json`: menções de novembro (empresa, CNPJ, data, seção, link e `matched_cnpj`).
   - `tests/fixtures/baseline/dou_api/*.json`: respostas brutas da API do DOU para uns 6 casos (CNPJ completo, filial, raiz isolada, trecho truncado, sem resultado, paginação), para testes offline.
   - `tests/fixtures/baseline/run_result_*.json`: o `return_value` (XCom) de 2 execuções reais de `exec_search`, para fixar o contrato de resultado.
4. Documentar em `plano/INVENTARIO.md` todos os pontos de contato com o Airflow e o Docker:
   - os imports `airflow.*` em `src/`;
   - as chamadas HTTP em `rodou_dashboard/app/services/airflow_service.py`, `routes/dags.py`, `routes/admin.py` e `services/dag_config_service.py`;
   - a leitura de logs do Airflow (`LOGS_DIR`), o uso de `docker compose` e `subprocess`, e as variáveis e conexões do Airflow em uso (`inlabs_portal`, `inlabs_db`, `path_tmp`, `smtp_default`).
5. Preparar o ambiente de desenvolvimento local: `pyproject.toml` na raiz com `uv`, Python 3.11 e grupos de dependências (`core`, `dashboard`, `dev`), sem instalar Airflow.

**Entregáveis:** tag e branch, fixtures, `plano/INVENTARIO.md`, `pyproject.toml`.

**Critério de aceite**
- `git status` limpo em `feature/modo-local`.
- As fixtures reproduzem 26 menções e 16 empresas.
- O inventário cobre 100% das ocorrências encontradas por `grep -rn "airflow\|api/v2\|LOGS_DIR\|docker\|subprocess"` em `src/` e `rodou_dashboard/app/`.

**Fora de escopo:** qualquer mudança de comportamento.

**Registro:** _(preencher)_

---

## Sprint 1: Núcleo sem Airflow e procedimento de upstream

**Objetivo:** importar e executar `src/` (buscadores, hooks, schemas, parsers, utils) num Python comum, sem instalar Airflow e sem editar os arquivos do upstream.

**Tarefas**
1. Criar `compat/airflow_shim/airflow/...` com os módulos e símbolos usados por `src/`, levantados no inventário. Mínimo:
   - `airflow.sdk.Variable.get(key, default=...)`, lendo de um provedor de configuração do Registrale (o SQLite do painel ou um dicionário em memória nos testes);
   - `airflow.sdk.bases.hook.BaseHook` com `get_connection(conn_id)`, devolvendo `host`, `login`, `password`, `port`, `schema` e `extra_dejson` a partir do mesmo provedor (conexões `inlabs_portal` e `inlabs_db`);
   - `airflow.providers.postgres.hooks.postgres.PostgresHook`, implementado com `psycopg`/SQLAlchemy (`get_pandas_df`, `get_sqlalchemy_engine`, `run`);
   - stubs que lancem `NotImplementedError` claro para o que o modo local não usa (DAG, operators, Slack, MSSQL, timetables, `send_email`).
2. Ativação explícita: `compat/bootstrap.py::install_airflow_shim()` insere o shim no `sys.path`, **só** se o Airflow real não estiver instalado.
3. Teste de cobertura do shim, `tests/local/test_shim_imports.py`: importa todos os módulos de `src/` exceto `dou_dag_generator.py`, `dag_load_inlabs/` e `utils/open_search/indexer.py`. Assim, se o upstream passar a usar um símbolo novo do Airflow, esse teste falha.
4. Rodar a suíte de `tests/` aplicável fora do Docker (`uv run pytest -m "not live"`). Marcar com `@pytest.mark.airflow` os testes que exigem Airflow real (geração e carregamento de DAG, e2e) e excluí-los no modo local.
5. Escrever `plano/UPSTREAM.md`:
   - procedimento de merge (`git fetch upstream`, `git merge upstream/main`, conflitos, testes);
   - lista de **patches locais** em arquivos do upstream (arquivo, motivo e trecho), começando pelos já existentes: `searchers.py` (busca por raiz), `hooks/inlabs_hook*.py` (regex de raiz, escape de apóstrofo), `schemas.py` (descarte de itens nulos), `dou_dag_generator.py` (YAML tolerante, DAGs temporárias sem agenda) e `dag_load_inlabs` (manutenção do INLABS, Datasets);
   - lista de **caminhos removidos** (vazia até o Sprint 8).
6. Criar `tools/sync_upstream.py`, que faz fetch e merge sem commit, re-remove os caminhos listados, mantém a nossa versão de `AGENTS.md`/`README.md`, roda os testes locais e imprime o relatório de conflitos. Testar com um merge de ensaio numa branch descartável.
7. Registrar os comandos do modo local na seção 6 do `AGENTS.md`.

**Entregáveis:** `compat/`, testes do shim, `plano/UPSTREAM.md`, `tools/sync_upstream.py`.

**Critério de aceite**
- `uv run pytest -m "not live and not airflow"` passa no Windows e no Linux, sem Airflow instalado.
- `git diff baseline-docker -- src/` não tem mudança feita neste sprint.
- O ensaio de `sync_upstream.py` termina com relatório e sem alterar `main`.

**Riscos:** o upstream pode depender de comportamento interno do Airflow (por exemplo, `Variable.get` com `deserialize_json`). Cubra o shim com testes para cada uso real.

**Registro:** _(preencher)_

---

## Sprint 2: Executor local (busca DOU) e camada de executor no painel

**Objetivo:** o painel executa rotinas sem o Airflow e produz exatamente as mesmas menções.

**Tarefas**
1. Criar `rodou_dashboard/app/runtime/runner.py`:
   - carrega um YAML com `src/parsers.py`;
   - para cada bloco `search`, chama os buscadores de `src/searchers.py` com os mesmos argumentos que `dou_dag_generator.perform_searches` usa (`reference_date` = data da execução);
   - devolve o mesmo dicionário que hoje vai para o XCom de `exec_search_N` (contrato fixado nas fixtures do Sprint 0).
2. Criar `rodou_dashboard/app/runtime/executor.py` com a interface `Executor`: `trigger(routine, date, **conf) -> run_id`, `status(run_id)`, `wait(run_ids, timeout)`, `result(run_id)`, `pause/unpause(routine)`, `last_runs(routine)`.
   - `AirflowExecutor` encapsula o código atual de `airflow_service.py`, sem mudança de comportamento.
   - `LocalExecutor` roda o runner num `ThreadPoolExecutor` (máximo de 2 rotinas simultâneas e 1 busca por dia por rotina) e grava as execuções na nova tabela `job_runs` (id, rotina, data, status, início, fim, erro, resultado em JSON).
3. Trocar no painel **todas** as chamadas ao Airflow listadas no inventário pela interface (`get_executor()`, escolhido por `REGISTRALE_EXECUTOR`). Estas funções passam a usar `executor.result`:
   - `fetch_mentions_from_dag_run`;
   - `get_last_search_time` / `get_next_search_time`, que hoje leem os logs do Airflow;
   - as "DAGs temporárias" da busca mensal e da busca avulsa (`temp_monthly_dou_*`, `temp_adhoc_dou_*`), que viram execuções do runner com um YAML em memória: nada de arquivo em `dag_confs/` nem descoberta pelo Airflow.
4. Remover do painel o fallback `docker compose exec` (`subprocess`) do `airflow_service`, ou isolá-lo no `AirflowExecutor`.
5. Testes:
   - runner com as fixtures da API do DOU (offline);
   - contrato de resultado comparado com `run_result_*.json`;
   - `LocalExecutor` com concorrência, timeout e erro;
   - **teste de paridade** `tests/local/test_parity_nov2026.py` (`@pytest.mark.live`): roda novembro no modo local e compara o conjunto (CNPJ, data, link) com `nov2026_mentions.json`.

**Entregáveis:** `runtime/runner.py`, `runtime/executor.py`, migração do painel, tabela `job_runs`, testes.

**Critério de aceite**
- Com `REGISTRALE_EXECUTOR=local` e o painel rodando fora do Docker, a busca de data única e a busca mensal de novembro/2026 geram **as mesmas 26 menções de 16 empresas** e o e-mail (via smtp4dev ou SMTP real) é montado igual.
- Com `REGISTRALE_EXECUTOR=airflow`, tudo continua funcionando como antes. Os testes do painel passam nos dois modos.

**Registro:** _(preencher)_

---

## Sprint 3: Agendador, servidor e ciclo de vida

**Objetivo:** o modo local roda sozinho todos os dias, num processo único e estável no Windows.

**Tarefas**
1. Criar o ponto de entrada `rodou_dashboard/app/runtime/server.py` (`uv run registrale`):
   - sobe o painel com **waitress** (1 processo, 8 threads);
   - inicializa o banco;
   - impede uma segunda instância com lock de arquivo no diretório de dados.
2. Criar `runtime/scheduler.py` com APScheduler (`BackgroundScheduler`, jobstore SQLite, timezone `America/Sao_Paulo`):
   - um job por rotina ativa, com o `schedule` (cron) do YAML, reconstruído quando o YAML muda (o painel já chama `touch_dag_generator`; substituir por `scheduler.reload()`);
   - o agendador do Google Sheets (`start_sheets_scheduler`) passa a ser job do mesmo scheduler, eliminando a duplicação;
   - política de execução perdida: se o PC estava desligado às 8h, executar ao ligar (`misfire_grace_time`, `coalesce=True`), uma vez por dia.
3. Diretório de dados por plataforma (`platformdirs`):
   - `database.db`, `logs/`, `inlabs/` e `rotinas/` (cópia gerenciada de `dag_confs/`);
   - variáveis de ambiente substituem os caminhos fixos (`/data`, `/dag_confs`, `/mnt/airflow-logs`) em `dag_config_service` e afins.
4. Logs em arquivo com rotação (`logs/registrale.log` e `logs/runs/<run_id>.log` por execução), visíveis no painel.
5. Rótulo correto de falhas: erro de SMTP depois da busca vira "Erro Envio E-mail" e não "Erro (Busca Mensal)". As menções continuam gravadas.
6. Rodar no Windows (máquina real ou VM) com `uv run registrale`.

**Entregáveis:** `runtime/server.py`, `runtime/scheduler.py`, diretórios configuráveis, logs.

**Critério de aceite**
- No Windows, sem Docker, o painel abre em `http://localhost:5000`, a rotina principal dispara no horário agendado (teste com um cron de 2 minutos à frente) e a sincronização do Sheets aparece **uma vez** por intervalo.
- Reiniciar o processo não perde agendamentos nem histórico.
- Uma execução perdida com o PC desligado roda ao ligar.

**Registro:** _(preencher)_

---

## Sprint 4: INLABS local

**Objetivo:** baixar e pesquisar o INLABS sem Docker, mantendo o modo SQL do upstream.

**Tarefas**
1. `runtime/pg_portable.py`:
   - usa os binários do PostgreSQL 17 para Windows embutidos (`windows/vendor/pgsql/`, sem instalador);
   - no primeiro uso, `initdb` em `%LOCALAPPDATA%\Registrale\pgdata` com senha gerada e guardada no SQLite;
   - `pg_ctl start/stop` atrelado ao ciclo de vida do app, porta livre detectada (padrão 54329) e escuta só em `127.0.0.1`;
   - cria o schema `dou_inlabs` com o `init-db.sql` existente e a extensão `unaccent`.
2. `runtime/inlabs_loader.py`, porta direta das tarefas de `dag_load_inlabs/ro_dou_inlabs_load_pg_dag.py`, reusando a lógica e não reescrevendo:
   - verificação de manutenção do portal, login com reaproveitamento de cookie, listagem e download dos ZIPs do dia;
   - extração **segura** (Zip Slip, limite de tamanho e de quantidade de arquivos);
   - parse dos XML e upsert por `id`;
   - limpeza dos temporários;
   - retenção de 120 dias (`enforce_inlabs_retention_limit` já existe no painel).
3. Conexões `inlabs_portal` e `inlabs_db` servidas pelo shim a partir das configurações do painel (usuário e senha do INLABS já salvos na tela de Integrações).
4. Ligar ao `LocalExecutor`: o download do dia vira job do agendador (horários do upstream: 06:59 e 23:59) e a busca mensal "baixar e pesquisar" usa o loader. A busca INLABS usa `INLABSSQLModeHook` sem mudança.
5. Testes: loader com ZIPs sintéticos (incluindo ZIP malicioso), `pg_portable` (start, stop, porta ocupada) e busca SQL contra o Postgres portátil com artigos sintéticos que cubram as regras de CNPJ por raiz.

**Critério de aceite**
- No Windows: o Postgres portátil sobe e desce com o app.
- Com o portal no ar, baixar um dia e pesquisá-lo gera as mesmas menções que a API do DOU para esse dia (diferenças são documentadas e explicadas).
- Com o portal em manutenção, o fallback para a API do DOU continua.
- **Se o portal estiver em manutenção durante o sprint**, a validação real fica pendente e é registrada; o critério é cumprido com testes sintéticos e revalidado no Sprint 7.

**Registro:** _(preencher)_

---

## Sprint 5: Arquivo do PDF integral do DOU

**Objetivo:** automatizar o que o analista faz à mão: guardar o PDF integral do DOU de cada dia numa pasta local.

**Tarefas**
1. Investigação (com tempo limitado, registrada no Registro): identificar a fonte oficial do PDF integral por seção e dia (download de PDF da edição no INLABS e/ou leitor do in.gov.br), formato de URL, autenticação, tamanho típico, edições extras e disponibilidade histórica. Escolher a fonte principal e uma alternativa.
2. `runtime/pdf_archiver.py`:
   - baixa os PDFs das seções configuradas para a data;
   - salva em `<pasta>\AAAA\MM\DOU_AAAA-MM-DD_Secao1.pdf` (e extras), de forma idempotente (pula o que já existe e valida tamanho e cabeçalho `%PDF`);
   - tenta de novo quando o portal falha.
3. Agendar junto da busca diária e permitir disparo manual por data e por mês no painel.
4. Tela de configurações: pasta de destino (padrão `Documentos\Registrale\DOU`), seções, ligar/desligar e status do último arquivamento.
5. Cada menção registra o caminho do PDF do dia, para abrir direto da lista de menções.

**Critério de aceite:** num dia útil, os PDFs das seções configuradas aparecem na pasta sem ação do analista, abrem corretamente e são equivalentes aos que ele baixa hoje à mão; rodar de novo não duplica arquivos.

**Fora de escopo (backlog, standby):** exportar só a página com a menção destacada.

**Registro:** _(preencher)_

---

## Sprint 6: Instalador Windows

**Objetivo:** instalação de um clique e uso diário sem terminal.

**Tarefas**
1. `windows/build.ps1`, script de build reprodutível:
   - baixa o Python 3.11 *embeddable* (versão fixa, com hash verificado) e instala as dependências travadas (`uv export` → `pip install --target`);
   - copia o app (`rodou_dashboard/`, `src/`, `compat/`, `dag_confs/`) e o PostgreSQL portátil;
   - gera `Registrale-Setup-<versão>.exe` com Inno Setup (`windows/installer.iss`).
2. Launcher `windows/launcher.pyw`:
   - ícone na bandeja com os itens Abrir painel, Status, Ver logs, Reiniciar e Sair;
   - sobe o servidor sem janela de console e abre o navegador;
   - atalho no Menu Iniciar e na Área de Trabalho, e início automático com o Windows (atalho em `shell:startup`, opcional no instalador).
3. Primeira execução:
   - assistente que **importa os dados atuais**: `data/database.db` do modo Docker (empresas, menções, configurações e templates) e rotinas de `dag_confs/`;
   - o backup é feito antes da importação.
4. Atualização:
   - o painel consulta as Releases do repositório e oferece "Atualizar";
   - o instalador novo preserva `%LOCALAPPDATA%\Registrale`;
   - migrações de banco versionadas (tabela `schema_version`).
5. Desinstalação mantém os dados, salvo se o usuário marcar a remoção.
6. CI: workflow `windows-build.yml` (runner `windows-latest`) que roda os testes do modo local, gera o instalador e publica o artefato com hash SHA-256 (publicação de release só com pedido do usuário).

**Critério de aceite:** numa VM Windows 10/11 limpa:
- instalar, abrir pelo atalho, importar o banco atual, ver as mesmas empresas e menções, rodar uma busca e receber o e-mail;
- reiniciar o Windows e o app volta sozinho;
- instalar a versão seguinte por cima preserva os dados.

**Registro:** _(preencher)_

---

## Sprint 7: Validação de paridade 100% e homologação

**Objetivo:** provar que o modo local substitui o Docker sem perda e obter a aprovação do usuário.

**Checklist (todos obrigatórios, com evidência no Registro)**
1. Paridade de busca, local × Docker, para a mesma rotina e as mesmas datas:
   - novembro/2026 completo (26 menções, 16 empresas);
   - um segundo mês completo escolhido pelo usuário;
   - 5 buscas de data única.
   
   Divergência zero, ou cada diferença explicada e aceita pelo usuário.
2. INLABS: pelo menos 3 dias baixados e pesquisados no modo local com o portal no ar, comparados à API do DOU.
3. Agendamento: 5 dias úteis seguidos de execução automática no PC do analista, sem intervenção, com e-mails recebidos.
4. PDFs: 5 dias úteis arquivados automaticamente.
5. Resiliência:
   - portal do DOU lento ou fora (timeouts);
   - INLABS em manutenção;
   - SMTP errado (menções gravadas, erro rotulado certo);
   - PC desligado no horário;
   - duas buscas simultâneas.
6. Instalação, atualização e desinstalação numa VM limpa (critério do Sprint 6).
7. Upstream: ensaio de `tools/sync_upstream.py` com o `upstream/main` do momento; os testes do modo local passam.
8. Desempenho: RAM em repouso abaixo de 400 MB, abertura em menos de 15 s e busca mensal comparável ao modo Docker.

**Entregável:** `plano/HOMOLOGACAO.md` com resultados, evidências e o termo **"Aprovado para remover Docker/Airflow"** assinado pelo usuário (registro de quem aprovou e quando).

**Registro:** _(preencher)_

---

## Sprint 8: Remoção de Docker/Airflow, limpeza do git e novo README

**Pré-condição:** aprovação registrada em `plano/HOMOLOGACAO.md`. Sem ela, este sprint não começa.

**Tarefas**
1. Remover Docker, Airflow e Kubernetes:
   - `Dockerfile`, `docker-compose*.yml`, `.dockerignore`, `Makefile`, `Makefile.backup`, `generate-Makefile.sh`, `instalar.bat`, `helm/`, `k8s/`, `docs/Dockerfile` e `docs/docker-compose.yml`;
   - `src/dou_dag_generator.py`, `dag_load_inlabs/` (lógica já portada para `runtime/inlabs_loader.py`; mover o `init-db.sql` para o runtime) e `src/utils/open_search/` (se não for usado);
   - testes exclusivos do Airflow (`@pytest.mark.airflow`);
   - `rodou_dashboard/Dockerfile`, `AirflowExecutor`, `airflow_service.py` e `REGISTRALE_EXECUTOR`, que passa a ser sempre local;
   - workflows de CI de Docker e Helm.
2. Atualizar `plano/UPSTREAM.md` com a lista final de **caminhos removidos** e validar `tools/sync_upstream.py` contra o `upstream/main`: o merge re-remove esses caminhos e os testes passam.
3. Limpeza do git, com confirmação do usuário a cada item destrutivo:
   - remover a worktree `Registrale-dou-sync` e a branch `upstream-sync` (já mergeada);
   - remover o stash `backup-pre-merge`;
   - remover os containers `sync-*` e as imagens antigas;
   - revisar o `.gitignore` (dados, build do Windows, `vendor/`);
   - remover arquivos de teste e rascunhos versionados por engano;
   - integrar `feature/modo-local` em `main` e criar a tag `v1.0.0`.
4. Reescrever o `README.md`: o que é, requisitos (Windows 10/11), instalação pelo `.exe`, primeiro uso (importação, integrações, planilha), uso diário, onde ficam dados, logs e PDFs, atualização do app, como receber atualizações do Ro-DOU (link para `plano/UPSTREAM.md`) e créditos e licença do Ro-DOU.
5. Atualizar o `AGENTS.md` para o estado pós-migração: remover as seções do modo Docker e a convivência dos dois modos.
6. Atualizar os manuais do painel (`rodou_dashboard/docs/`, `MANUAL.md`) que citam Docker, Airflow ou `make`.

**Critério de aceite**
- `grep -rni "docker\|airflow\|helm\|make run" --exclude-dir=.git` só retorna o shim (`compat/airflow_shim`), o histórico (`CHANGELOG.md`) e a seção de upstream.
- O instalador gerado a partir de `main` passa o checklist do Sprint 6.
- Um ensaio de sync com o upstream passa.
- Nenhuma branch, worktree ou stash obsoleta.

**Registro:** _(preencher)_

---

## Backlog

- **Exportar a página com a menção destacada (standby):** gerar, para cada menção, o PDF só da página do DOU onde a empresa aparece, com o CNPJ destacado, salvo junto do PDF do dia. Depende do Sprint 5 (fonte do PDF e localização da página: `numberpage` no INLABS e `pdfpage` no XML).
- Busca opcional por razão social (citações sem CNPJ, como despachos do CADE), marcada como "por nome" e sujeita a revisão, por causa dos falsos positivos.
- Não enviar segredos ao navegador na página de configurações (hoje o HTML do usuário master contém senhas e a chave do Google), e não apagar tokens salvos quando o campo for enviado vazio.
- Tempo limite menor com mais tentativas na API do DOU (10 s × 5 em vez de 35 s × 3) para dias de portal instável.
