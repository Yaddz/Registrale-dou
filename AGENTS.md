# Guia de agentes do Registrale-DOU

Este arquivo orienta qualquer agente (humano ou IA) que trabalhe neste repositório. Vale para todo o projeto a partir da raiz; instruções em subdiretórios prevalecem apenas no próprio escopo.

**Antes de qualquer tarefa da migração, leia [`plano/PLANO.md`](plano/PLANO.md)** e trabalhe somente no sprint indicado no seu prompt (`plano/prompts/`). O plano é a fonte da verdade sobre escopo, ordem e critérios de aceite; este arquivo define como trabalhar.

## 1. O que é o projeto

O Registrale-DOU monitora publicações do Diário Oficial da União (DOU) que citam as empresas clientes de um escritório (identificadas por CNPJ) e avisa o analista por e-mail. É um fork do [Ro-DOU](https://github.com/gestaogovbr/Ro-dou) (clipping de diários oficiais do governo federal) com um painel web próprio.

**Contexto de uso, que guia todas as decisões:**

- Um único analista, numa máquina **Windows** com permissão de administrador. Hospedar em servidor foi descartado.
- Hoje roda via Docker (Airflow 3 + PostgreSQL + painel Flask). **Destino: aplicativo Windows instalável (.exe), sem Docker e sem Airflow**, conforme `plano/PLANO.md`.
- O analista guarda o PDF integral do DOU numa pasta local como registro.
- O projeto **precisa continuar recebendo atualizações do Ro-DOU oficial** (remote `upstream`). Isso restringe o quanto se pode alterar em `src/` (seção 4).

## 2. Mapa do repositório

| Caminho | Papel | Origem |
|---|---|---|
| `src/` | Núcleo de busca: `schemas.py`/`parsers.py` (contrato YAML), `searchers.py` e `hooks/` (DOU, INLABS, QD, DOE-SP), `notification/`, `ai/`, `utils/` | **Upstream** (Ro-DOU), com patches locais mínimos |
| `src/utils/cnpj.py` | Regra de identificação de empresa pela **raiz do CNPJ** (matriz, filiais, raiz isolada) | Local |
| `src/dou_dag_generator.py` | Gera DAGs do Airflow a partir dos YAML | Upstream; sai no Sprint 8 |
| `dag_load_inlabs/` | DAG de carga do INLABS (XML → PostgreSQL) | Upstream + patches; portado no Sprint 4 |
| `dag_confs/` | Rotinas de busca em YAML. `Pesquisa_cnpj.yaml` é a rotina principal, **gerada pelo painel** | Local (exemplos em `examples_and_tests/` são do upstream) |
| `rodou_dashboard/` | Painel Flask (`app/routes`, `app/services`, `templates/index.html` com Alpine.js), SQLite em `data/database.db` | Local |
| `rodou_dashboard/app/services/airflow_service.py` | Única porta de saída para o Airflow (há chamadas diretas remanescentes em `routes/dags.py`, `routes/admin.py`, `services/dag_config_service.py`) | Local |
| `tests/` | Testes do núcleo (pytest) | Upstream + local |
| `rodou_dashboard/tests/` | Testes do painel | Local |
| `plano/` | Plano de migração e prompts por sprint | Local |
| `Dockerfile`, `docker-compose*.yml`, `Makefile`, `helm/`, `docs/` | Infra e documentação do Ro-DOU | Upstream; Docker/Airflow/Helm saem no Sprint 8 |

Artefatos locais nunca são fonte do produto: `mnt/`, `data/`, `flask_sessions/`, `schemas/`, `__pycache__`, `.pytest_cache`, logs e builds.

### Fluxos principais

- **Empresas:** Google Sheets (e/ou GestãoClick) → `sheets_service`/`sync_cnpj` → tabela `companies` → `dag_config_service.rebuild_yaml_from_db()` → `dag_confs/Pesquisa_cnpj.yaml` (blocos de até 1.500 CNPJs).
- **Busca:** YAML → `parsers.py` → `schemas.py` → buscador (`DOUSearcher` via API in.gov.br ou `INLABSSearcher` via PostgreSQL) → resultado no formato `grupo → termo → departamento → itens`.
- **Menções:** o painel lê o resultado da execução (hoje via XCom do Airflow em `fetch_mentions_from_dag_run`), grava em `mentions` e envia e-mail com `email_service`.
- **Busca mensal:** `routes/dags.py::api_trigger_monthly`. Se o portal INLABS estiver em manutenção, cai para a API do DOU.

## 3. Regras de negócio que não podem regredir

1. **CNPJ por raiz.** A empresa é identificada pelos 8 primeiros caracteres do CNPJ. Conta como menção: CNPJ completo de qualquer estabelecimento da raiz, raiz pontuada isolada (`24.684.423`, padrão das Resoluções-RE da ANVISA) e raiz destacada pela própria busca do DOU (o trecho da API pode vir truncado). **Não** conta: raiz sem pontos, número maior que contenha a raiz, valor monetário (`R$ 24.684.423,00`). A implementação única fica em `src/utils/cnpj.py` e o painel a espelha em `mention_service._cnpj_branch_regex`; mantenha as duas em sincronia, com testes (`tests/cnpj_utils_test.py`).
2. **A API do DOU só acha CNPJ formatado.** Consulte sempre pela raiz no formato `"XX.XXX.XXX"`: uma consulta cobre matriz e filiais.
3. **Seções da rotina principal:** Seções 1, 2, 3 e Edições Extras.
4. **CNPJ alfanumérico** (12 alfanuméricos + 2 dígitos) deve continuar aceito.
5. **Menções são gravadas antes do envio de e-mail.** Falha de SMTP nunca pode descartar menções.
6. **INLABS indisponível** (o portal responde HTTP 200 com página de "Manutenção Programada") → busca pela API do DOU, sem acumular retries.
7. **Datas:** o painel aceita `DD/MM/AAAA`, `DD/MM/AA` e ISO, e converte tudo para `AAAA-MM-DD` (`airflow_service.normalize_date_str`) antes de executar.
8. **Baseline de paridade:** novembro/2026 (01–23/11), rotina principal → **26 menções de 16 empresas** (25 pares empresa/dia: 22 com CNPJ completo e 3 só pela raiz). Qualquer executor novo precisa reproduzir isso (Sprint 2 e Sprint 7).

## 4. Compatibilidade com o Ro-DOU oficial (upstream)

O `remote upstream` é `https://github.com/gestaogovbr/Ro-dou`. As atualizações entram por merge (o procedimento final está em `plano/UPSTREAM.md`, criado no Sprint 1).

- **Não reescreva arquivos de `src/`** para eliminar o Airflow. O núcleo roda fora do Airflow por meio do pacote de compatibilidade `compat/airflow_shim/` (Sprint 1), que fornece os símbolos `airflow.*` usados por `src/`. Se o upstream passar a importar um símbolo novo, amplie o shim, não o arquivo do upstream.
- Todo patch local em arquivo do upstream deve ser **pequeno, comentado em português e registrado** em `plano/UPSTREAM.md` (arquivo, motivo, como reaplicar). Prefira colocar a lógica nova em módulos novos (como `src/utils/cnpj.py`) e chamá-la com uma linha.
- Código do modo local (executor, agendador, carga INLABS, launcher Windows) fica **fora de `src/`**, em `rodou_dashboard/app/runtime/` e `windows/`.
- Arquivos do upstream removidos por decisão do projeto (Docker, Airflow, Helm, gerador de DAGs) ficam listados em `plano/UPSTREAM.md`, para que o merge os remova de novo automaticamente.
- `AGENTS.md` e `README.md` são **nossos**; em conflito de merge, mantenha a nossa versão e incorpore manualmente só o que for útil.

## 5. Fluxo de trabalho

1. Leia o sprint correspondente em `plano/PLANO.md` e o código e os testes diretamente envolvidos.
2. Rode `git status --short`. Pode haver trabalho de outros agentes; não reverta, não formate e não inclua alterações alheias.
3. Faça a menor mudança coesa que cumpra o critério de aceite. Não antecipe sprints futuros.
4. Enquanto o Sprint 7 não for aprovado, **os dois modos convivem**: `REGISTRALE_EXECUTOR=airflow` (Docker, atual) e `REGISTRALE_EXECUTOR=local` (novo). Nada pode quebrar o modo Docker antes do Sprint 8.
5. Adicione ou ajuste testes junto do comportamento alterado; rode os testes focados e depois a suíte.
6. Atualize a documentação do sprint (seção "Registro" do sprint em `plano/PLANO.md`) com o que foi feito, as decisões, os comandos de validação e os resultados.
7. Revise o diff final: só mudanças intencionais, sem segredos, dados ou caches.

**Git:** não crie commits, branches, tags nem push sem pedido explícito do usuário. Quando pedido, use os prefixos `feat:`, `fix:`, `docs:`, `chore:`, `refactor:` e `test:`, em português. Trabalhe em `feature/modo-local` (criada no Sprint 0), não em `main`.

## 6. Ambiente e comandos

### Modo Docker (atual, até o Sprint 8)

Em Linux/Fedora com Podman, `docker-compose.override.yml` ajusta o SELinux (`:z`) e as portas do smtp4dev (2525/1143).

```bash
docker compose up -d postgres airflow-api-server      # primeiro: migra o banco do Airflow
docker compose up -d --no-deps airflow-scheduler airflow-dag-processor smtp4dev dashboard
docker exec -w /opt/airflow airflow-scheduler python -m pytest -q tests -m "not live" --ignore=tests/test_e2e_dag_execution.py
```

- Painel: `http://localhost:5000`; Airflow: `http://localhost:8080` (API v2 com token JWT em `POST /auth/token`).
- Testes do painel: copie `rodou_dashboard/tests` para o container `rodou-dashboard` e rode `pytest` em `/app`. As 2 falhas `user_manual` são preexistentes (falta `MANUAL.md` na imagem).
- O painel em gunicorn usa código montado por volume: depois de editar `rodou_dashboard/`, **reinicie** o container `rodou-dashboard`. O Airflow recarrega `src/` sozinho em cerca de 30 s.

### Modo local (a partir do Sprint 1)

Python 3.11 + `uv` (sem Airflow instalado; o núcleo `src/` roda sobre `compat/airflow_shim/` via `compat/bootstrap.py::install_airflow_shim()`).

```bash
uv sync --group dev                                  # instala Python 3.11 e dependências locais
uv run pytest tests/ -m "not live and not airflow"   # suíte do núcleo sem Airflow/rede
uv run pytest -m "not live and not airflow"          # suíte completa (núcleo + painel)
uv run python tools/sync_upstream.py                 # sincroniza com upstream/main (ver plano/UPSTREAM.md)
```

- Ponto de entrada do servidor local (`uv run registrale`): definido no Sprint 3.

### Rede

Testes unitários **nunca** dependem de rede: use mocks. Testes que acessam o DOU ou o INLABS reais levam `@pytest.mark.live` e ficam fora da suíte padrão. O portal in.gov.br costuma travar requisições por até 35 s; não trate lentidão como bug sem medir.

## 7. Papéis

### Implementação

- Trace o fluxo completo antes de mudar: `YAML → parsers → schemas → searcher/hook → resultado → painel (menções, e-mail)`.
- Preserve o formato de resultado `grupo → termo → departamento → itens` e as chaves já consumidas pelo painel (`abstract`, `date`, `section`, `href`, `title`, `matched_cnpj`, `is_branch`, `root_only`).
- Integrações externas sempre com timeout, retries limitados e mensagens de erro úteis.
- No Windows: nada de gunicorn, `fork`, caminhos fixos com `/` ou dependência de WSL. Use `pathlib` e o diretório de dados do usuário (`%LOCALAPPDATA%\Registrale`).

### Revisão (independente, somente leitura)

- Revise o diff do sprint contra o critério de aceite: regressões, casos-limite, concorrência (agendador e threads), idempotência (buscas repetidas não duplicam menções), uso de rede e memória, e compatibilidade com o upstream (patches em `src/` registrados?).
- Liste os achados por severidade, com arquivo:linha, impacto e correção sugerida. Não corrija durante a revisão.

### Segurança

- Fronteiras: YAML, nomes de arquivo de rotina (já protegidos contra path traversal em `routes/dags.py`), ZIPs do INLABS (Zip Slip e bomba de ZIP), HTML vindo do DOU (escapar e sanitizar), credenciais (SMTP, INLABS, GestãoClick, Google) e o instalador/atualizador (só baixar de origem confiável e verificar hash).
- **Nunca** exiba, registre em log ou versione segredos. As configurações salvas no SQLite contêm senhas e a chave privada do Google: não as envie ao navegador nem as copie para fixtures. Se encontrar um segredo real, informe só o local e o tipo.

### Testes

- Cubra sucesso, erro e limites, de forma determinística (sem data corrente, rede ou credenciais reais).
- A paridade entre os modos é testada com fixtures gravadas a partir do modo Docker (Sprint 0) e com a comparação de menções da baseline de novembro/2026.

## 8. Segredos, dados e operações destrutivas

- Não leia nem exiba `.env`, `data/database.db` (tabela `settings`) ou credenciais sem necessidade estrita.
- Não apague volumes, bancos, containers, branches, worktrees, stashes ou arquivos sem autorização explícita. O Sprint 8 só começa depois da aprovação escrita do usuário ao final do Sprint 7.
- Antes de qualquer migração de dados, faça backup de `data/database.db` (e do Postgres, se houver).
- Use dados sintéticos em fixtures; publicações reais só quando indispensável e sem dados pessoais.

## 9. Critério de conclusão de qualquer tarefa

- O critério de aceite do sprint foi cumprido e demonstrado (comandos e resultados no Registro do sprint).
- Os testes aplicáveis passam nos dois modos enquanto ambos existirem.
- Os patches em arquivos do upstream estão registrados em `plano/UPSTREAM.md`.
- Nenhum segredo, cache, dado local ou arquivo alheio entrou no diff.
- O relatório final lista os arquivos alterados, as validações feitas, o que não pôde ser validado e por quê.
