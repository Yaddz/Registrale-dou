# Changelog — Registrale-DOU

Histórico de versões do aplicativo desktop **Registrale-DOU** (Windows).  
O histórico anterior ao fork (base **Ro-DOU**, até `0.14.0`) está arquivado em [`docs/upstream/CHANGELOG.md`](docs/upstream/CHANGELOG.md) e no repositório oficial do [Ro-DOU](https://github.com/gestaogovbr/Ro-dou).

---

## [Não publicado]

### Documentação
- **Manual reescrito** em linguagem direta, organizado por tarefa (primeiros passos, empresas, rotinas e buscas, menções e relatórios, PDFs, configurações, problemas comuns e glossário) e conferido contra a interface atual.
- **Aba Manual do painel** passa a mostrar o próprio `docs/manual/` (`GET /api/manual?format=sections`), com índice e pesquisa. O manual antigo em HTML fixo, que ainda falava em "Ro-DOU Dashboard" e no assistente de integrações removido, saiu da tela.
- Decisões de arquitetura, baseline, resultado da homologação, pendências e backlog consolidados em `docs/tecnico/02_decisoes_e_historico.md`. Plano de migração, prompts de sprint, homologação e inventário do Airflow saíram do git (`docs/projeto/` agora é local e ignorado).
- `AGENTS.md` sem dependência do plano de sprints, com roteiro "Comece aqui" e as regras de filtro de órgão e SMTP.

### Interface
- Submenu de Configurações (abaixo de 1280 px) passa a exibir degradê nas bordas e setas (`chevron-left`/`chevron-right`) quando há pílulas fora da área visível, rolando automaticamente para manter a seção ativa visível.

### Corrigido
- Isolamento de `tests/local/`: fixture `autouse` em `tests/local/conftest.py` redireciona `REGISTRALE_DATA_DIR` e `REGISTRALE_LOGS_DIR` para `tmp_path`.
- **Histórico de buscas quando o envio de e-mail falha:** buscas diárias e mensais passam a registrar `Busca Concluída` (ou `Busca Concluída com Pendências`) / `Busca Mensal Concluída` antes do evento `Erro Envio E-mail`, preservando todas as menções gravadas no banco.
- **Siglas de órgão em rotinas personalizadas antigas:** o executor local expande siglas de `department` em memória ao carregar qualquer rotina (`runner.load_specs`), sem exigir que a rotina seja salva novamente.
- **Sincronização do GestãoClick (duplicidade, erros silenciosos, URL padrão, precedência e contagens):**
  - Segundo clique ou agendamento simultâneo de sincronização do GestãoClick agora retorna HTTP 409 ("Já existe uma sincronização do GestãoClick em andamento") e o botão **Sincronizar** fica desabilitado enquanto `sync_active` estiver ativo.
  - HTTP 404 ou 401/403 na página 1 e retorno vazio da API do GestãoClick passam a gerar erro explícito no histórico em vez de "Sincronização OK" com 0 clientes.
  - URL padrão do GestãoClick alterada para `https://api.gestaoclick.com` (sem `/franquias`); URLs salvas que terminem em `/clientes` têm esse sufixo removido ao montar a requisição.
  - **Precedência de origens:** a planilha **Google Sheets** agora tem prioridade sobre o **GestãoClick** (atualiza nome, status e assume a origem `Google Sheets`; o GestãoClick não sobrescreve empresas da planilha nem manuais).
  - Registros repetidos retornados pela API são deduplicados por CNPJ antes da gravação (prevalece o último ativo) e o evento `Sincronização OK` registra as contagens reais (`novas`, `atualizadas`, `sem mudança`, `preservadas` e `repetidos na API`).
  - `/api/activity` passa a expor `sync_started_at` e `sync_elapsed_s`; sincronização sem resposta há mais de 20 minutos gera aviso na Visão geral e sincronização interrompida ao fechar o programa é fechada como `Erro Sync` na partida seguinte.
- **Sincronização do GestãoClick não gravava as empresas no banco.** A busca terminava, gerava o JSON e o YAML e registrava "Sincronização OK", mas a tabela `companies` ficava intacta: a thread do botão rodava sem app context e o passo de reserva (`sync_json_to_db`) lia o JSON numa pasta errada. Agora a gravação acontece dentro de `executar_sincronizacao` (origem "Manual" preservada) e erro de banco vira "Erro Sync" no histórico.
- **Sincronização travava com mais de 1.500 empresas.** `get_routines()` comparava com o banco só os CNPJs do 1º bloco da rotina principal, reconstruía o YAML a cada listagem e, dentro do `reload` do agendador (trava não reentrante), entrava em deadlock. A contagem soma todos os blocos e a trava do agendador passou a ser reentrante.
- **Servidor órfão depois de fechar o programa.** Se o launcher morresse sem passar pelo **Sair** (Gerenciador de Tarefas, travamento, logoff), o servidor continuava rodando com o código antigo e segurando a porta 5000; ao reabrir, o servidor novo falhava com "Outra instância" e o painel seguia no processo velho. Agora o servidor fica num Job Object do Windows (morre junto com o launcher), o servidor grava o PID em `registrale.pid` e o launcher encerra um órfão desse mesmo `python.exe` antes de subir, e uma segunda cópia do launcher só avisa que o programa já está aberto.
- Legendas da **Limpeza do sistema** diziam o contrário do que os botões fazem: **Limpar menções** apaga todas as menções (não só as "lidas") e **Limpar histórico** apaga o histórico de eventos (não "arquivos de cache").

---

## [1.3.2] — 2026-11-25 (Avisos, SMTP, contador de menções e responsividade)

### Interface
- Submenu de Configurações (abaixo de 1280 px) passa a exibir degradê nas bordas e setas (`chevron-left`/`chevron-right`) quando há pílulas fora da área visível, rolando automaticamente para manter a seção ativa visível.

### Corrigido
- Isolamento de `tests/local/`: fixture `autouse` em `tests/local/conftest.py` redireciona `REGISTRALE_DATA_DIR` e `REGISTRALE_LOGS_DIR` para `tmp_path`.
- **Aviso "Integrações pendentes" permanente removido**, junto com o assistente antigo de integrações. A Visão geral só avisa sobre problema real: envio de e-mail ligado sem servidor, rotina principal sem destinatário com o SMTP ligado, Google Sheets/GestãoClick com sincronização automática ligada e sem credenciais, ou erro de integração nas últimas 24 h. Integração desligada nunca gera aviso. O botão **Resolver** leva direto à aba certa (`/api/system/health_alerts`).
- **SMTP desligado por padrão.** Sem a chave `enabled`, o envio fica desligado (antes valia como ligado e cada busca gerava "conexão recusada"). Ligado sem servidor, nada é enviado e a execução registra um único evento "SMTP ligado sem servidor configurado". A tela segue a mesma regra. Instalações antigas com servidor e usuário configurados continuam ligadas.
- **Contador de menções da tela Empresas** soma as menções pela raiz do CNPJ (matriz, filiais e menções só pela raiz) e é atualizado sozinho quando uma busca termina.
- Aviso "INLABS local não instalado" deixou de aparecer: é a configuração padrão do instalador, não um problema.
- Ícones animados presos: o "Atualizar" de Armazenamento (e de outras duas listas em Configurações) girava sem parar, o envio de e-mail de teste ficava pulsando e duas setas podiam ficar viradas. A animação passou para um elemento em volta do ícone, que o Lucide não substitui.
- GestãoClick com sincronização automática desligada e credenciais do INLABS (INLABS local não instalado) aparecem esmaecidas e travadas, como o SMTP desligado; a "Fonte quando o INLABS estiver fora" continua editável.

### Interface
- Menu lateral vira gaveta abaixo de 768 px e começa recolhido abaixo de 1024 px.
- Empresas em cartões em telas estreitas; tabela mais enxuta (Origem só a partir de 1280 px).
- Tabelas de menções (aba Menções, menções recentes da Visão geral e Relatórios): coluna Empresa/CNPJ com largura mínima de 240 px e nome em até 2 linhas (nome completo ao passar o mouse); trecho truncado; coluna Ações sempre visível de 800 a 1920 px.
- Submenu de Configurações em pílulas roláveis abaixo de 1280 px; cartões de Limpeza do sistema sem transbordo.
- Cabeçalho compacto (botões só com ícone abaixo de 768 px); filtros de Menções quebram linha.
- Seletores de arquivo no padrão do design system (botão "Escolher arquivo" e nome do arquivo escolhido).
- Seções e agendamento legíveis nos cartões de rotina ("Seção 1", "Dias úteis às 08:00"); avisos (toasts) nunca com tipo indefinido.

---

## [1.3.1] — 2026-11-25 (Hotfix: buscas sem resultado)

### Interface
- Submenu de Configurações (abaixo de 1280 px) passa a exibir degradê nas bordas e setas (`chevron-left`/`chevron-right`) quando há pílulas fora da área visível, rolando automaticamente para manter a seção ativa visível.

### Corrigido
- Isolamento de `tests/local/`: fixture `autouse` em `tests/local/conftest.py` redireciona `REGISTRALE_DATA_DIR` e `REGISTRALE_LOGS_DIR` para `tmp_path`.
- **Busca mensal não executava nenhum dia.** Os disparos da thread de fundo (`routes/dags.py::api_trigger_monthly`) rodavam fora do app context e o executor falhava com `Working outside of application context`, erro que era engolido; a busca terminava como "Nenhuma menção encontrada". Agora cada disparo roda dentro do app context, o servidor vincula o app ao executor na inicialização (`get_executor(app)`) e falhas de disparo geram o evento **"Erro (Busca Mensal)"** com o motivo.
- **Filtro de órgão por sigla descartava todas as publicações.** O núcleo compara o filtro com os elementos de `hierarchyList` do DOU (nome oficial). Siglas comuns (ANVISA, INPI, MS, MAPA, INMETRO, ANP, ANATEL, ANS, ANEEL, ANTT, IBAMA, CADE, RFB…) agora são convertidas para o nome oficial ao gravar o YAML (`services/organ_aliases.py`); o painel continua mostrando o que o usuário digitou.
- Limpar o filtro de órgão na rotina principal não tinha efeito: `rebuild_yaml_from_db()` tratava a lista vazia salva como ausente e herdava o filtro antigo do YAML. Agora lista vazia significa "todos os órgãos" e a chave `organs` antiga sai do bloco.
- Texto de ajuda do campo "Órgãos específicos" orienta a usar o nome do órgão como aparece no DOU.

---

## [1.3.0] — 2026-11-25 (Sprints 11 a 16)

### Busca e confiabilidade (Sprint 11)
- Busca diária sem dependência do PostgreSQL portátil do INLABS quando ausente no instalador (`-SkipPostgresDownload`).
- Fim dos erros repetidos `NoneType is not iterable` no log ao consultar o INLABS indisponível.
- Rastreamento de cobertura por seção (Seções 1, 2, 3 e Edição Extra) com status **"Concluída com pendências"** (`partial`) quando falta seção ou confirmação.
- Nova tentativa automática no mesmo dia (intervalo de 60 min, até 4 tentativas, até 22h), enviando e-mail apenas das menções novas.
- Confirmação obrigatória pela API do DOU (`strict_confirm`) quando há filtro de órgão (`department`) na rotina.
- Alinhamento dos parâmetros padrão da rotina principal com a baseline (`department: []`, `is_exact_search: false`, `field: TUDO`, Seções 1/2/3 + `EDICAO_EXTRA`).

### Configurações, SMTP e atividade (Sprint 12)
- Interruptores de ativar/pausar unificados num único modelo visual e persistindo o estado no banco.
- Assistente de configuração reconhecendo corretamente integrações e rotinas pausadas.
- Interruptor global de SMTP desligado desabilita campos de e-mail dependentes, permite salvar sem destinatários e bloqueia envios em todo o app mantendo o registro de menções.
- Interruptor padronizado para o arquivamento de PDFs do DOU.
- Painel de atividade visível para tarefas em segundo plano e botão **Atualizar** na barra de ações.

### Interface e armazenamento de PDFs (Sprint 13)
- Ajustes visuais na barra lateral recolhida, cards de alerta, tela do Google Sheets (campo de intervalo de sincronização) e template de e-mail.
- Nova aba **Armazenamento** exibindo os meses de PDFs arquivados e o espaço ocupado em disco.

### Onboarding completo (Sprint 14)
- Assistente guiado de primeiro uso cobrindo pasta e organização dos PDFs, rotina inicial, cadastro de empresas (manual, Google Sheets ou GestãoClick), SMTP, INLABS e resumo final.

### Documentação unificada e limpeza (Sprint 15)
- Consolidação da documentação em `docs/` (`manual/`, `tecnico/`, `upstream/` e `projeto/`), removendo duplicatas e páginas de Docker/WSL/Kubernetes do MkDocs.
- Manual único do analista atualizado cobrindo os Sprints 11 a 14, consumido diretamente pelo painel (`/api/manual`) e pelo instalador.
- Limpeza de sobras locais do repositório e separação do `CHANGELOG.md` próprio do Registrale-DOU.

---

## [1.2.0] — 2026-11-24 (Sprints 9 e 10)

### Novidades
- Janela própria no Windows via `pywebview` (WebView2), com fallback automático para o navegador padrão e minimização para a bandeja do sistema.
- Ícone oficial do Registrale-DOU aplicado no executável e atalhos do instalador.
- Escolha da pasta e do layout de organização dos PDFs do DOU (`ano_mes`, `ano`, `nenhum`) no primeiro acesso e em Configurações.
- Status detalhado do arquivamento de PDFs, máscara de data (`DD/MM/AAAA`), seletor de mês e exibição da última sincronização.
- Avisos dispensáveis no painel, interruptor de ativação/desativação do SMTP e remoção da lista de clientes do pacote do instalador.
- Login opcional no acesso local (`localhost`).

---

## [1.1.0] — 2026-11-24 (Sprints 6.1 a 8)

### Novidades
- Remoção completa de Docker, Apache Airflow e gunicorn; execução 100% local com **Waitress** + **APScheduler** e shim de compatibilidade (`compat/airflow_shim/`).
- Contingência automática para INLABS indisponível ou em manutenção via busca no **PDF integral do DOU** (`pesquisa.in.gov.br`) com confirmação na API do DOU (`inlabs_fallback`: `pdf` | `api` | `off`).
- Validação de paridade de 100% com a baseline de novembro/2026 (26 menções de 16 empresas, incluindo identificação apenas pela raiz de CNPJ).

---

## [1.0.0] — 2026-11-23 (Sprints 0 a 6)

### Lançamento do aplicativo Windows
- Instalador nativo para Windows (`Registrale-Setup-x.y.z.exe`) com Python 3.11 *embeddable* e Inno Setup, sem necessidade de Docker ou WSL.
- Launcher na bandeja do sistema (`windows/launcher.pyw`) com inicialização automática com o Windows.
- Executor local (`LocalExecutor`) com persistência de execuções em `job_runs` (SQLite) e logs rotacionados por execução.
- Arquivamento automático dos PDFs integrais do DOU e suporte opcional ao PostgreSQL portátil para carga INLABS.
- Migração de dados de instalações anteriores e verificador de atualizações via GitHub Releases com validação SHA-256.
