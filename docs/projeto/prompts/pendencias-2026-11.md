# Plano — pendências de novembro/2026

> Prompts de execução para um agente (Sonnet). **Uma etapa por sessão**, na ordem da tabela.
> Antes de começar qualquer etapa: leia `AGENTS.md` (raiz) e a seção 4 de
> `docs/tecnico/02_decisoes_e_historico.md`. Trabalhe **somente** na etapa indicada.
> Não crie commits, branches, tags nem push, exceto na Etapa 0 e na Etapa 7, e só com autorização
> escrita do usuário no chat.
>
> Ao fim de cada etapa: testes focados + `uv run pytest -m "not live"` (no Bash do Windows, se `uv`
> não estiver no PATH, use `.venv/Scripts/python.exe -m pytest -m "not live"`), `CHANGELOG.md`
> em `[Não publicado]`, manual (`docs/manual/`) se o analista vê a mudança, e a seção 4 de
> `docs/tecnico/02_decisoes_e_historico.md` atualizada (tirar o que foi resolvido).
> Teste de interface sempre numa **cópia** dos dados (`REGISTRALE_DATA_DIR` + `--port 5055`),
> nunca na instalação real; larguras de 800 a 1920 px, temas claro e escuro.
> **Não** aplique nada no app instalado (`%LOCALAPPDATA%\Programs\Registrale`): isso vai pelo
> próximo instalador, que está fora deste plano.

## Fora do escopo (decisão do usuário)

INLABS real, acompanhamento de 5 dias de uso real, PostgreSQL portátil no instalador, busca por
razão social, segredos em `GET /api/settings` e geração/aplicação do instalador com as correções.

## Decisões já tomadas (não reabrir)

| Pendência | Decisão |
|---|---|
| Planilha × GestãoClick para o mesmo CNPJ | **A planilha manda.** |
| URL padrão do GestãoClick | **`https://api.gestaoclick.com`** (sem `/franquias`), que foi a que funcionou com a conta real (19.750 registros). |
| Lista antiga de CNPJs na release `v1.0.0` | **Trocar o asset da release**; o histórico do git fica como está. |

## Ordem das etapas

| Etapa | Pendências | Tamanho | Pode começar quando |
|---|---|---|---|
| 0 | Commitar o trabalho atual (pend. 7) | P | Agora, com autorização |
| 1 | Sincronização do GestãoClick (pend. 1 a 6) | M | Etapa 0 feita (ou recusada) |
| 2 | Histórico de buscas e filtro de órgão (pend. 10 e 11) | P | Etapa 1 revisada |
| 3 | Isolamento de testes e interface (pend. 12, 13 e 14) | P | Etapa 1 revisada (paralela à 2, sem tocar nos mesmos arquivos) |
| 4 | API do DOU instável (pend. 22) | P | Etapa 2 revisada |
| 5 | PDF da página destacada (pend. 19) | G | Etapas 2 e 4 revisadas |
| 6 | Nova tentativa automática ao vivo (pend. 9) | P (validação) | Etapa 2 revisada; rodar entre 13h e 17h |
| 7 | Asset da release `v1.0.0` (pend. 15) | P | Qualquer momento, com autorização |

Depois de cada etapa, uma sessão separada de revisão com `revisao.md` (trocando `<N>` por
"pendências — Etapa N"). Só avance com veredito "aprovado".

---

## Etapa 0 — Commitar o trabalho atual (pend. 7)

**Só execute com autorização do usuário no chat.** Hoje o repositório tem dois blocos de
trabalho sem commit, de sessões diferentes:

1. Correções de 25/11 (sessão Opus): sincronização do GestãoClick gravando no banco, deadlock no
   `reload` do agendador e servidor órfão do launcher. Arquivos:
   `rodou_dashboard/app/services/sync_cnpj.py`, `rodou_dashboard/app/services/dag_config_service.py`,
   `rodou_dashboard/app/routes/admin.py` (**só** o trecho de `manual_sync_route`),
   `rodou_dashboard/app/runtime/scheduler.py`, `rodou_dashboard/app/runtime/server.py`,
   `windows/launcher.pyw`, `rodou_dashboard/tests/conftest.py`,
   `rodou_dashboard/tests/test_gestaoclick_persistencia.py`, `tests/local/test_launcher_lifecycle.py`,
   `tests/local/test_sprint11_busca.py`, a entrada do manual em
   `docs/manual/07_atualizacao_e_problemas.md` ("já está aberto") e as entradas do `CHANGELOG.md`.
2. Manual reescrito e aba Manual (outra sessão): `docs/manual/*`, `docs/tecnico/*`,
   `rodou_dashboard/app/services/manual_service.py`, o resto de `admin.py` (rota `/manual`),
   `templates/index.html`, `static/css/registrale.css`, `tests/test_dashboard.py`, `AGENTS.md`,
   `README.md`, `.gitignore`, `.github/workflows/windows-build.yml`.

Passos:
1. `git status --short` e `git diff --stat`. Confirme que nada de `docs/projeto/`, `data/`,
   `database.db`, `.env` ou `dag_confs/Pesquisa_cnpj.yaml` está no diff.
2. Rode a suíte completa; ela precisa estar verde antes de commitar.
3. Proponha ao usuário **dois** commits (use `git add -p` no `admin.py` e no `CHANGELOG.md` para
   separar os blocos):
   - `fix: sincronização do GestãoClick grava no banco, deadlock do agendador e servidor órfão`
   - `docs: manual reescrito e aba Manual renderizando docs/manual`
4. Commit só depois do "sim" dele. Sem push, a menos que ele peça.

---

## Etapa 1 — Sincronização do GestãoClick (pend. 1 a 6)

Contexto: em 25/11 a sincronização passou a gravar no banco (`sync_cnpj.salvar_clientes_no_banco`)
e a rotina é reconstruída por `dag_config_service.rebuild_yaml_from_db()`. Seis problemas
continuam. Arquivos centrais: `rodou_dashboard/app/services/sync_cnpj.py`,
`rodou_dashboard/app/services/sheets_service.py`, `rodou_dashboard/app/routes/admin.py`
(`manual_sync_route`, `_sync_running`, status em ≈ linha 482), `rodou_dashboard/app/runtime/scheduler.py`
(`_run_scheduled_gestaoclick_sync`), `rodou_dashboard/app/services/health_alerts.py` e `templates/index.html`.

### T1. Barrar sincronização duplicada (pend. 1)
Em 25/11, dois cliques às 20:34 abriram duas sincronizações; a segunda esperou o
`COMPANY_SYNC_LOCK` e baixou tudo de novo (+3 min).
1. Em `manual_sync_route`, marque `_sync_running = True` **na requisição**, sob `_sync_state_lock`,
   antes de criar a thread (hoje é marcado dentro da thread, o que deixa a corrida aberta). Se já
   estiver `True`, responda **409** com `{"status": "error", "message": "Já existe uma sincronização do GestãoClick em andamento."}`.
2. A execução agendada (`_run_scheduled_gestaoclick_sync`) também deve respeitar e marcar o
   mesmo estado; mova `_sync_running`/`_sync_state_lock` para um módulo de serviço (ex.:
   `services/sync_state.py`) para a rota e o agendador usarem o mesmo, sem import circular.
3. No front, desabilite o botão **Sincronizar** enquanto o status (`sync_active`) indicar
   sincronização em andamento e mostre o toast de aviso no 409.
4. Testes: segundo POST com uma sincronização em andamento → 409 e `executar_sincronizacao`
   chamado uma vez só; agendada com manual em andamento → não roda.

### T2. Zero registros não é sucesso (pend. 2)
Em 25/11 às 20:01, com a URL base `.../clientes`, a página 1 respondeu 404, `get_monitored_data`
tratou como "fim dos registros" e o histórico gravou "Sincronização OK" com 0 clientes.
1. Em `get_monitored_data`: 404 **na página 1** é erro (`GestaoClickError` ou `ValueError`) com a
   mensagem "A API do GestãoClick respondeu 404 em <url>. Confira a URL base em Configurações →
   Integrações (padrão: https://api.gestaoclick.com)." 404 em página > 1 continua sendo fim.
2. Em `executar_sincronizacao`: lista vazia levanta erro claro ("A API do GestãoClick não
   retornou nenhum cliente") em vez de `return` silencioso. O chamador já grava "Erro Sync".
3. 401/403 na página 1: erro "Credenciais do GestãoClick recusadas (HTTP <código>)".
4. Testes para os três casos.

### T3. URL padrão sem `/franquias` (pend. 3)
1. `GESTAOCLICK_DEFAULT_BASE_URL = "https://api.gestaoclick.com"` em `sync_cnpj.py`.
2. Troque todos os placeholders e padrões em `templates/index.html` (≈ linhas 838, 3453, 3895,
   5653, 6004), `docs/tecnico/03_integracoes.md`, `04_referencia_da_api.md`,
   `05_guia_operacional_e_build.md` e os testes que usam `/franquias`. Procure com
   `grep -rn franquias` (fora de `.venv`).
3. **Não** altere um valor que o usuário já salvou. Se um `gestaoclick_base_url` salvo terminar
   em `/clientes`, remova esse sufixo ao montar a URL (era o erro das 20:01) e registre um aviso no log.

### T4. A planilha manda sobre o GestãoClick (pend. 4)
Regra nova, valendo para empresas com o mesmo `cnpj_norm`:
- **Manual**: ninguém altera (como hoje).
- **Sincronização da planilha** (`sheets_service`): cria as que não existem e atualiza nome e
  status de qualquer empresa que não seja Manual. Quando atualizar uma de origem `GestãoClick`,
  muda a origem para `Google Sheets`.
- **Sincronização do GestãoClick** (`salvar_clientes_no_banco` e `sync_json_to_db`): cria as que
  não existem e atualiza **só** as de origem `GestãoClick`. Não toca em `Google Sheets` nem em `Manual`.

Documente a regra em `docs/manual/02_empresas.md` e em `docs/tecnico/03_integracoes.md`. Testes:
o mesmo CNPJ nas duas fontes, em qualquer ordem de sincronização, termina com o nome e o status
da planilha e origem `Google Sheets`.

### T5. Contagem honesta (pend. 5)
A API devolve 19.750 registros para 18.494 CNPJs distintos, e o log mostra "19.750 atualizadas" mesmo sem mudança.
1. Deduplique por `cnpj_norm` antes de gravar (se repetir, vale o último registro com
   `ativo=1`; se nenhum for ativo, o último). Registre no log quantos registros eram repetidos.
2. `salvar_clientes_no_banco` devolve `novas`, `atualizadas` (só quando nome ou status mudou de
   fato), `sem_mudanca` e `ignoradas` (Manual ou da planilha). Grave isso nos detalhes do evento
   "Sincronização OK" no histórico, ex.: "18.494 clientes (1.256 repetidos na API): 0 novas,
   3 atualizadas, 18.369 sem mudança, 122 da planilha preservadas".

### T6. Sincronização travada visível (pend. 6)
Em 25/11 a sincronização ficou presa num deadlock e o histórico parou em "Sincronização Iniciada", sem aviso.
1. Guarde `started_at` junto do estado da T1. O status (`admin.py` ≈ linha 482) passa a expor
   `sync_started_at` e `sync_elapsed_s`.
2. Em `health_alerts.py`: se houver sincronização (GestãoClick ou planilha) em andamento há mais
   de 20 min, mostre o alerta "A sincronização do GestãoClick está sem resposta há N min. Use
   Reiniciar no ícone da bandeja." com o botão **Resolver** levando a Configurações → Integrações.
3. Na partida do servidor (`runtime/server.py`, depois de `create_app`), se o último evento de
   sincronização no `sync_history` for "Sincronização Iniciada" sem um "OK" ou "Erro" depois,
   grave "Erro Sync — Sincronização interrompida (o programa foi fechado durante a sincronização)".
4. Testes com relógio simulado (sem `sleep` real).

---

## Etapa 2 — Histórico de buscas e filtro de órgão (pend. 10 e 11)

### T1. Falha de e-mail não apaga a conclusão (pend. 10)
`rodou_dashboard/app/routes/dags.py`:
- **Busca diária** (≈ linhas 1082–1119): quando `email_failed` é `True`, a busca não registra
  "Busca Concluída" (só "Erro Envio E-mail"). Registre também "Busca Concluída" (ou "Busca
  Concluída com Pendências", se houver `pending_sections`) com " (e-mail falhou; menções
  gravadas)" no motivo. A ordem dos eventos fica: conclusão primeiro, depois o erro de e-mail.
- **Busca mensal** (≈ linhas 2150–2175): no `except` do envio, registre "Busca Mensal Concluída"
  com "N menções gravadas; o envio do relatório falhou" antes do "Erro Envio E-mail".
- Testes com `EmailSender.send_custom_email` levantando `SMTPException`: as menções continuam
  no banco (regra 5 do `AGENTS.md`) e o histórico tem conclusão + erro.

### T2. Siglas de órgão em rotinas antigas (pend. 11)
Hoje `expand_organ_filters` só é aplicado ao salvar uma rotina (`dags.py` ≈ linha 351), na
rotina principal (`dag_config_service.py` ≈ linha 567) e nas buscas avulsa/mensal (≈ linhas
1250 e 1965). Uma rotina personalizada antiga, gravada com "ANVISA", ainda falha na execução agendada.
1. Ache o ponto único em que o executor local carrega o YAML de uma rotina antes de chamar o
   núcleo (`rodou_dashboard/app/runtime/executor.py` ou `runner.py`) e aplique
   `expand_organ_filters` a `department` de cada bloco de `search`, **em memória** (não grave o arquivo).
   **Não altere `src/`.**
2. Teste: rotina personalizada com `department: ["ANVISA"]` executada pelo agendador chega ao
   buscador com "Agência Nacional de Vigilância Sanitária".

---

## Etapa 3 — Isolamento de testes e interface (pend. 12, 13 e 14)

Não toque em arquivos das Etapas 1 e 2 (`sync_cnpj.py`, `sheets_service.py`, `dags.py`, `admin.py`).

### T1. Testes não escrevem na pasta real (pend. 12)
1. Em `tests/local/conftest.py`, acrescente uma fixture `autouse` que aponte
   `REGISTRALE_DATA_DIR` (e, se existir, `REGISTRALE_LOGS_DIR`) para `tmp_path`, para nenhum teste
   cair em `%LOCALAPPDATA%\Registrale`. Atenção aos módulos que leem o diretório na importação:
   confira em `runtime/paths.py` se `get_logs_dir()` é resolvido a cada chamada.
2. Prova: liste `%LOCALAPPDATA%\Registrale\logs\runs` antes e depois de
   `pytest tests/local -m "not live"`. **Nenhum arquivo novo.** Cole as duas contagens no relatório.

### T2. Teste da pasta de PDFs no Windows (pend. 13)
Em 25/11, `test_open_pdf_storage_folder_validation_and_launch` passou no Windows (suíte completa
verde, 741 testes). Confirme com
`pytest -k test_open_pdf_storage_folder_validation_and_launch`. Se passar, só tire a pendência
de `02_decisoes_e_historico.md`. Se falhar, mocke `os.startfile` (Windows) além de `subprocess.Popen`.

### T3. Pílulas de Configurações e checklist de interface (pend. 14)
1. Abaixo de 1280 px, a fileira de pílulas das 9 subabas de Configurações (`templates/index.html`)
   rola na horizontal sem indicar que há mais itens. Mostre um degradê nas bordas com conteúdo
   escondido e setas (`btn-icon`, Lucide `chevron-left`/`chevron-right`) que rolam a fileira; ao
   trocar de subaba, a pílula ativa rola para a área visível (`scrollIntoView({inline: 'nearest'})`).
   Siga `docs/tecnico/06_design_system.md`.
2. Rode o checklist da seção 7 de `06_design_system.md` **com o login ligado** (usuário `master`
   e usuário `user`), em 800, 1024, 1280 e 1920 px, nos temas claro e escuro, numa cópia dos
   dados na porta 5055. Registre o resultado em `02_decisoes_e_historico.md` (o que passou e o
   que foi corrigido).

---

## Etapa 4 — API do DOU instável (pend. 22)

`src/hooks/dou_hook.py::_request_page` usa `timeout = 35` e `max_retries = 3` fixos (patch local
registrado em `docs/tecnico/UPSTREAM.md`). O backlog sugere 10 s × 5, mas o `AGENTS.md` lembra
que o portal costuma travar por até 35 s. **Meça antes de mudar.**
1. Medição (`@pytest.mark.live` ou script em `tools/`, fora da suíte padrão): 40 consultas reais
   com termos da rotina de teste (`tests/local/rotina_teste.py`), registrando a latência de cada
   uma. Calcule p50, p95 e o máximo. Cole no relatório.
2. Escolha `timeout` = o menor valor ≥ p95 × 1,5 entre 10, 15, 20 e 35 s; `max_retries` tal que
   o tempo total no pior caso fique ≤ 35 s × 3 (o comportamento de hoje), considerando o backoff.
3. Patch mínimo em `dou_hook.py`: ler `REGISTRALE_DOU_TIMEOUT` e `REGISTRALE_DOU_MAX_RETRIES` do
   ambiente, com os padrões escolhidos, em uma ou duas linhas comentadas em português.
   Atualize a linha de `dou_hook.py` em `docs/tecnico/UPSTREAM.md` (o que mudou e como reaplicar).
4. Teste offline: `requests.get` simulado com `Timeout` confirma o número de tentativas e o
   timeout usado, com e sem as variáveis de ambiente.

---

## Etapa 5 — PDF da página destacada (pend. 19)

Para cada menção, gerar um PDF só com a página do DOU em que a empresa aparece, com o CNPJ destacado.
1. Fonte: o PDF integral do dia já arquivado (`runtime/pdf_archiver.py`, pasta configurada,
   layouts `ano_mes`/`ano`/`nenhum`) e o texto por página de `runtime/pdf_search.py`. Sem PDF do
   dia arquivado, a menção fica sem página destacada (não baixe sob demanda nesta etapa).
2. Localize a página: procure o CNPJ completo **e** a raiz pontuada isolada, com a mesma regra de
   `src/utils/cnpj.py` (raiz, matriz e filiais; nada de valor monetário). Use a função existente,
   não duplique a regex.
3. Gere com `pypdf` (já é dependência): extraia a página e acrescente anotações de destaque
   (`Highlight`) nas ocorrências. Se a posição exata do texto não for confiável, desenhe um
   retângulo em volta da linha ou, no mínimo, entregue só a página. Documente qual foi possível.
4. Guarde em `<pasta dos PDFs>/destaques/<AAAA-MM-DD>/<cnpj_raiz>_<id_menção>.pdf`, gere na
   gravação da menção (em segundo plano, sem atrasar o e-mail) e grave o caminho na menção
   (migração em `runtime/migrations.py`, com backup do `database.db` antes).
5. Painel: na aba Menções, botão **Página destacada** (Lucide `file-search`) quando existir; no
   e-mail, um link ou anexo opcional atrás de uma configuração `email_attach_highlight` (desligada por padrão).
6. Testes com PDF sintético de 3 páginas gerado no próprio teste (CNPJ na página 2): a página
   extraída é a 2 e tem o destaque; menção sem PDF arquivado → sem arquivo e sem erro.
7. Manual: `docs/manual/04_mencoes_e_relatorios.md` e `05_pdfs_do_dou.md`.

---

## Etapa 6 — Nova tentativa automática ao vivo (pend. 9)

Validação, não implementação. Só corrija algo se a validação falhar, e então descreva o defeito
antes de mexer no código.
1. Copie `%LOCALAPPDATA%\Registrale` para uma pasta temporária e suba
   `uv run registrale --port 5055` com `REGISTRALE_DATA_DIR` apontando para a cópia. Na cópia, troque
   os destinatários de e-mail da rotina principal por um endereço de teste ou desligue o SMTP.
   **Nunca** envie e-mail para clientes.
2. Entre 13h e 17h de um dia útil, dispare a busca do dia. Se todas as seções já estiverem
   publicadas, force a pendência na cópia (ex.: `inlabs_fallback=pdf` com a Edição Extra ainda
   não publicada, ou o PDF de uma seção removido do cache da cópia) e descreva como forçou.
3. Confirme e registre: status "Concluída com pendências"; job de nova tentativa no agendador
   para +60 min; a segunda execução roda sozinha e só notifica menções novas; o limite de 4
   tentativas e o corte das 22h estão corretos (leia o código e confira os horários reais dos jobs).
4. Resultado em `02_decisoes_e_historico.md` (seção 3, homologação): data, horário, evidências.

---

## Etapa 7 — Asset da release `v1.0.0` (pend. 15)

**Ação externa (GitHub): só com autorização explícita do usuário no chat, depois de mostrar o plano.**
1. `gh release view v1.0.0` e liste os assets. Confirme qual instalador contém
   `dag_confs/Pesquisa_cnpj.yaml` com CNPJs de clientes (abra o `.exe` com 7-Zip numa pasta
   temporária; não copie a lista para lugar nenhum nem a cole no relatório).
2. Mostre ao usuário o que vai ser feito: apagar o asset e editar as notas da release com
   "Instalador retirado: use a versão mais recente (v1.3.2 ou posterior)". Execute após o "sim".
3. Registre a decisão e a data em `02_decisoes_e_historico.md` (o histórico do git continua com o
   arquivo antigo, por decisão do usuário).
