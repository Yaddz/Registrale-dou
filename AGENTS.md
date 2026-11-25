# Guia de agentes do Registrale-DOU

Este arquivo orienta qualquer agente (humano ou IA) que trabalhe neste repositório. Vale para todo o projeto a partir da raiz; instruções em subdiretórios prevalecem apenas no próprio escopo.

**Antes de qualquer tarefa da migração, leia [`docs/projeto/PLANO.md`](docs/projeto/PLANO.md)** e trabalhe somente no sprint indicado no seu prompt (`docs/projeto/prompts/`). O plano é a fonte da verdade sobre escopo, ordem e critérios de aceite; este arquivo define como trabalhar.

## 1. O que é o projeto

O Registrale-DOU monitora publicações do Diário Oficial da União (DOU) que citam as empresas clientes de um escritório (identificadas por CNPJ) e avisa o analista por e-mail. É um fork do [Ro-DOU](https://github.com/gestaogovbr/Ro-dou) (clipping de diários oficiais do governo federal) com um painel web próprio.

**Contexto de uso, que guia todas as decisões:**

- Um único analista, numa máquina **Windows** com permissão de administrador. Hospedar em servidor foi descartado.
- Aplicativo Windows instalável (`.exe` via Inno Setup + Python 3.11 *embeddable*), sem Docker e sem Airflow, conforme `docs/projeto/PLANO.md`.
- O analista guarda o PDF integral do DOU numa pasta local (`Documentos\Registrale\DOU` por padrão, configurável no primeiro uso e em Configurações nos layouts `ano_mes`, `ano` ou `nenhum`) como registro.
- O painel abre em janela própria (`pywebview`/WebView2) controlada pelo `windows/launcher.pyw` na bandeja do sistema, com fallback automático para o navegador padrão.
- O projeto **precisa continuar recebendo atualizações do Ro-DOU oficial** (remote `upstream`). Isso restringe o quanto se pode alterar em `src/` (seção 4).

## 2. Mapa do repositório

| Caminho | Papel | Origem |
|---|---|---|
| `src/` | Núcleo de busca: `schemas.py`/`parsers.py` (contrato YAML), `searchers.py` e `hooks/` (DOU, INLABS, QD, DOE-SP), `notification/`, `ai/`, `utils/` | **Upstream** (Ro-DOU), com patches locais mínimos |
| `src/utils/cnpj.py` | Regra de identificação de empresa pela **raiz do CNPJ** (matriz, filiais, raiz isolada) | Local |
| `compat/` | Shim `airflow.*` (`compat/airflow_shim/`, `compat/bootstrap.py`) para rodar `src/` sem Airflow | Local |
| `dag_confs/` | Rotinas de busca em YAML. `Pesquisa_cnpj.yaml` é a rotina principal, **gerada pelo painel** | Local (exemplos em `examples_and_tests/` são do upstream) |
| `rodou_dashboard/` | Painel Flask (`app/routes`, `app/services`, `app/runtime/`, `templates/index.html` com Alpine.js), SQLite em `database.db` | Local |
| `windows/` | Launcher de bandeja (`launcher.pyw`), build (`build.ps1`) e instalador (`installer.iss`) | Local |
| `tests/` | Testes do núcleo e do modo local (`tests/local/`) | Upstream + local |
| `rodou_dashboard/tests/` | Testes do painel | Local |
| `docs/` | Documentação unificada: `manual/`, `tecnico/`, `upstream/` e `projeto/` (plano e prompts) | Local + upstream |

Artefatos locais nunca são fonte do produto: `data/`, `dist/`, `__pycache__`, `.pytest_cache`, logs e builds.

### Fluxos principais

- **Empresas:** Google Sheets (e/ou GestãoClick) → `sheets_service`/`sync_cnpj` → tabela `companies` → `dag_config_service.rebuild_yaml_from_db()` → `dag_confs/Pesquisa_cnpj.yaml` (blocos de até 1.500 CNPJs).
- **Busca:** YAML → `parsers.py` → `schemas.py` → `runtime/runner.py` (buscador `DOUSearcher` via API `in.gov.br` ou `INLABSSearcher` via PostgreSQL portátil) → resultado no formato `grupo → termo → departamento → itens`.
- **Menções:** o painel executa a busca via `LocalExecutor` (`runtime/executor.py`), lê o resultado em `job_runs`, grava em `mentions` e envia e-mail com `email_service`.
- **Busca mensal:** `routes/dags.py::api_trigger_monthly`. Se o portal INLABS estiver em manutenção ou indisponível, usa a contingência configurada (`pdf` ou `api`).

## 3. Regras de negócio que não podem regredir

1. **CNPJ por raiz.** A empresa é identificada pelos 8 primeiros caracteres do CNPJ. Conta como menção: CNPJ completo de qualquer estabelecimento da raiz, raiz pontuada isolada (`24.684.423`, padrão das Resoluções-RE da ANVISA) e raiz destacada pela própria busca do DOU (o trecho da API pode vir truncado). **Não** conta: raiz sem pontos, número maior que contenha a raiz, valor monetário (`R$ 24.684.423,00`). A implementação única fica em `src/utils/cnpj.py` e o painel a espelha em `mention_service._cnpj_branch_regex`; mantenha as duas em sincronia, com testes (`tests/cnpj_utils_test.py`).
2. **A API do DOU só acha CNPJ formatado.** Consulte sempre pela raiz no formato `"XX.XXX.XXX"`: uma consulta cobre matriz e filiais.
3. **Seções da rotina principal:** Seções 1, 2, 3 e Edições Extras.
4. **CNPJ alfanumérico** (12 alfanuméricos + 2 dígitos) deve continuar aceito.
5. **Menções são gravadas antes do envio de e-mail.** Falha de SMTP nunca pode descartar menções.
6. **INLABS indisponível ou não instalado** (o instalador padrão usa `-SkipPostgresDownload`, sem PostgreSQL portátil; ou o portal responde "Manutenção Programada" / o banco não tem o dia) → nunca pesquisar um banco vazio nem emitir erros repetidos de `NoneType`. O runner (`runtime/runner.py::_run_inlabs_fallback`) usa o **texto do PDF integral** do dia (`runtime/pdf_search.py`, PDFs de `pesquisa.in.gov.br`, sem login) e confirma na API do DOU só as empresas achadas para gravar o link da matéria (confirmação obrigatória com `strict_confirm` quando há filtro de órgão `department`); se o PDF falhar, cai para a API do DOU com todos os termos. Cada seção esperada do dia (Seções 1, 2, 3 e Extra) tem cobertura registrada; se faltar seção ou confirmação, a execução termina como **"Concluída com pendências"** (`partial`) e agenda nova tentativa automática no mesmo dia (a cada 60 min, até 4 tentativas e até as 22h, enviando e-mail só das menções novas). Configuração `inlabs_fallback` = `pdf` (padrão) | `api` | `off` em `global_settings` ou `REGISTRALE_INLABS_FALLBACK`. Os padrões da rotina principal seguem a baseline (`department: []`, `is_exact_search: false`, `field: TUDO`, Seções 1/2/3 + `EDICAO_EXTRA`).
7. **Datas:** o painel aceita `DD/MM/AAAA`, `DD/MM/AA` e ISO, e converte tudo para `AAAA-MM-DD` (`runtime/executor.py::normalize_date_str`) antes de executar.
8. **Baseline de paridade:** novembro/2026 (01–23/11), rotina principal → **26 menções de 16 empresas** (25 pares empresa/dia: 22 com CNPJ completo e 3 só pela raiz). Qualquer executor novo precisa reproduzir isso (Sprint 2 e Sprint 7).

## 4. Compatibilidade com o Ro-DOU oficial (upstream)

O `remote upstream` é `https://github.com/gestaogovbr/Ro-dou`. As atualizações entram por merge (o procedimento final está em `docs/tecnico/UPSTREAM.md`, criado no Sprint 1).

- **Não reescreva arquivos de `src/`** para eliminar o Airflow. O núcleo roda fora do Airflow por meio do pacote de compatibilidade `compat/airflow_shim/` (Sprint 1), que fornece os símbolos `airflow.*` usados por `src/`. Se o upstream passar a importar um símbolo novo, amplie o shim, não o arquivo do upstream.
- Todo patch local em arquivo do upstream deve ser **pequeno, comentado em português e registrado** em `docs/tecnico/UPSTREAM.md` (arquivo, motivo, como reaplicar). Prefira colocar a lógica nova em módulos novos (como `src/utils/cnpj.py`) e chamá-la com uma linha.
- Código do modo local (executor, agendador, carga INLABS, launcher Windows) fica **fora de `src/`**, em `rodou_dashboard/app/runtime/` e `windows/`.
- Arquivos do upstream removidos por decisão do projeto (Docker, Airflow, Helm, gerador de DAGs, MkDocs) ficam listados em `docs/tecnico/UPSTREAM.md`, para que o merge os remova de novo automaticamente.
- `AGENTS.md`, `README.md` e `CHANGELOG.md` são **nossos**; em conflito de merge, mantenha a nossa versão e incorpore manualmente só o que for útil.

## 5. Fluxo de trabalho

1. Leia o sprint correspondente em `docs/projeto/PLANO.md` e o código e os testes diretamente envolvidos.
2. Rode `git status --short`. Pode haver trabalho de outros agentes; não reverta, não formate e não inclua alterações alheias.
3. Faça a menor mudança coesa que cumpra o critério de aceite. Não antecipe sprints futuros.
4. Adicione ou ajuste testes junto do comportamento alterado; rode os testes focados e depois a suíte.
5. Atualize a documentação do sprint (seção "Registro" do sprint em `docs/projeto/PLANO.md`) com o que foi feito, as decisões, os comandos de validação e os resultados.
6. Revise o diff final: só mudanças intencionais, sem segredos, dados ou caches.

**Git:** não crie commits, branches, tags nem push sem pedido explícito do usuário. Quando pedido, use os prefixos `feat:`, `fix:`, `docs:`, `chore:`, `refactor:` e `test:`, em português.

## 6. Ambiente e comandos

Python 3.11 + `uv` (sem Airflow instalado; o núcleo `src/` roda sobre `compat/airflow_shim/` via `compat/bootstrap.py::install_airflow_shim()`).

```bash
uv sync --group dev                                  # instala Python 3.11 e dependências locais
uv run registrale                                    # inicia o servidor Waitress + APScheduler em http://127.0.0.1:5000
uv run pytest tests/ -m "not live"                   # suíte do núcleo
uv run pytest -m "not live"                          # suíte completa (núcleo + painel)
uv run python tools/sync_upstream.py                 # sincroniza com upstream/main (ver docs/tecnico/UPSTREAM.md)
```

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
- Não apague volumes, bancos, containers, branches, worktrees, stashes ou arquivos sem autorização explícita.
- Antes de qualquer migração de dados, faça backup de `database.db` (`%LOCALAPPDATA%\Registrale`).
- Use dados sintéticos em fixtures; publicações reais só quando indispensável e sem dados pessoais.

## 9. Critério de conclusão de qualquer tarefa

- O critério de aceite do sprint foi cumprido e demonstrado (comandos e resultados no Registro do sprint).
- Os testes aplicáveis passam sem regressões (`uv run pytest -m "not live"`).
- Os patches em arquivos do upstream estão registrados em `docs/tecnico/UPSTREAM.md`.
- Nenhum segredo, cache, dado local ou arquivo alheio entrou no diff.
- O relatório final lista os arquivos alterados, as validações feitas, o que não pôde ser validado e por quê.
