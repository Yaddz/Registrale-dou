# 01. Visão Geral e Arquitetura do Sistema

O **Ro-DOU Dashboard** é a interface web corporativa e orquestradora do ecossistema de monitoramento de Diários Oficiais da Registrale. Ele centraliza a gestão de empresas cadastradas, controla o disparo das rotinas de busca no Diário Oficial da União (DOU) e na base histórica do INLABS, gerencia notificações e exporta relatórios executivos.

---

## 🏗️ 1. Arquitetura Geral

```
                    ┌──────────────────────────────────────────────┐
                    │               Usuário / Browser             │
                    │   (Alpine.js + Tailwind CSS + Lucide Icons)  │
                    └──────────────────────┬───────────────────────┘
                                           │ HTTP / JSON REST API
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │            Flask Web Application             │
                    │          (Gunicorn WSGI / Port 5000)         │
                    └──────┬───────────────┬────────────────┬──────┘
                           │               │                │
            ┌──────────────▼──────┐ ┌──────▼──────┐ ┌───────▼──────────────┐
            │   SQLite Database   │ │ YAML Configs│ │ Background Workers   │
            │ (/data/dashboard.db)│ │(Airflow DAG)│ │ - Mentions Watcher   │
            │ - Users, Companies  │ │- Pesquisa_  │ │ - Sheets Scheduler   │
            │ - Mentions, History │ │  cnpj_*.yaml│ └──────────────────────┘
            │ - Settings,Template │ └─────────────┘
            └─────────────────────┘
                       ▲
                       │
       ┌───────────────┴───────────────┐
       │     Bases e APIs Externas     │
       ├───────────────────────────────┤
       │ • GestãoClick (API Clientes)  │
       │ • Google Sheets API v4        │
       │ • PostgreSQL INLABS (Matérias)│
       │ • Servidor SMTP (E-mails)     │
       │ • Apache Airflow (Execução)   │
       └───────────────────────────────┘
```

---

## 🛠️ 2. Stack Tecnológica

| Componente | Tecnologia | Finalidade |
| :--- | :--- | :--- |
| **Linguagem** | Python 3.10+ | Lógica de backend, integração e processamento de dados |
| **Framework Web** | Flask (<2.3.0) + Blueprints | Roteamento REST, views HTML e controle de sessão |
| **Sessão** | Flask-Session (Filesystem) | Gerenciamento de sessões com expiração de 30 min |
| **ORM & DB Local** | Flask-SQLAlchemy / SQLite | Persistência rápida de empresas, menções, configurações e usuários |
| **DB Histórico DOU** | PostgreSQL (`pg8000`) | Leitura de artigos e matérias capturadas do INLABS |
| **Servidor WSGI** | Gunicorn (2 workers + jitter) | Execução concorrente com reciclagem de memória |
| **Frontend Reativo** | Alpine.js | Estado reativo no cliente sem necessidade de build |
| **Estilização** | Tailwind CSS (via CDN) | Interface moderna, responsiva e com suporte a modais |
| **Exportações** | ReportLab + Pandas + OpenPyXL | Geração de PDFs diagramados e planilhas Excel nativas |
| **Feriados** | Algoritmo Computus de Butcher | Cálculo dinâmico de feriados nacionais fixos e móveis para identificar dias úteis com circulação do DOU |

---

## 🗄️ 3. Modelagem do Banco de Dados (SQLite)

O banco de dados SQLite principal fica localizado no volume persistente `/data/dashboard.db` (ou no diretório raiz em modo standalone). Ele é otimizado automaticamente na inicialização com os seguintes PRAGMAs de alta concorrência:
* `PRAGMA journal_mode=WAL;` (Write-Ahead Logging para leitura e escrita simultâneas)
* `PRAGMA busy_timeout=5000;` (Evita travamentos sob concorrência)
* `PRAGMA synchronous=NORMAL;` (Maior velocidade de escrita segura)

### Tabelas do Sistema:

1. **`users` (`User`)**
   * `id` (INTEGER, PK)
   * `username` (VARCHAR(50), UNIQUE)
   * `password_hash` (VARCHAR(256)) — Hash seguro gerado via `werkzeug.security`
   * `role` (VARCHAR(20)) — Nível de acesso: `'master'` (gerenciamento total) ou `'user'` (apenas consulta)
   * `created_at` (DATETIME)

2. **`companies` (`Company`)**
   * `id` (INTEGER, PK)
   * `nome` (VARCHAR(200)) — Razão Social ou Nome Fantasia
   * `cnpj` (VARCHAR(50), UNIQUE) — CNPJ normalizado e formatado
   * `origem` (VARCHAR(50)) — Origem do cadastro: `'gestaoclick'`, `'google_sheets'` ou `'manual'`
   * `status` (BOOLEAN) — Se a empresa está ativa para monitoramento diário no DOU
   * `created_at` / `updated_at` (DATETIME)

3. **`mentions` (`Mention`)**
   * `id` (INTEGER, PK)
   * `data` (VARCHAR(20)) — Data da publicação no DOU (formato `DD/MM/YYYY`)
   * `empresa` (VARCHAR(200)) — Nome da empresa detectada
   * `cnpj` (VARCHAR(50)) — CNPJ da empresa detectada
   * `secao` (VARCHAR(50)) — Seção do DOU (`SECAO_1`, `SECAO_2`, `SECAO_3`)
   * `trecho` (TEXT) — Trecho destacado do texto oficial onde o termo/CNPJ foi localizado
   * `link` (TEXT) — URL oficial para a página da publicação na Imprensa Nacional
   * `detected_at` (DATETIME) — Data e hora exatas da detecção

4. **`sync_history` (`SyncHistory`)**
   * `id` (INTEGER, PK)
   * `data` (VARCHAR(50)) — Data e hora do evento formatada (`DD/MM/YYYY HH:MM:SS`)
   * `evento` (VARCHAR(255)) — Título ou categoria do evento
   * `detalhes` (TEXT) — Descrição detalhada da execução (ex: número de registros importados)
   * **Método de Classe `SyncHistory.log_event(evento, detalhes, max_history=50)`:** Método centralizado que registra o evento e gerencia automaticamente a rotação FIFO da tabela, mantendo no máximo os últimos 50 registros no banco de dados.

5. **`inlabs_download_log` (`InlabsDownloadLog`)**
   * `id` (INTEGER, PK)
   * `date_str` (VARCHAR(10), UNIQUE) — Data do DOU baixada (formato `YYYY-MM-DD`)
   * `downloaded_at` (VARCHAR(50)) — Timestamp de quando o download foi finalizado
   * `status` (VARCHAR(20), default `'success'`) — Status da operação de carga
   * Esta tabela rastreia quais datas de edições do DOU foram baixadas com sucesso do portal INLABS para o banco PostgreSQL local, permitindo ao sistema identificar lacunas para buscas mensais.

6. **`settings` (`Settings`)**
   * `id` (INTEGER, PK)
   * `key` (VARCHAR(100), UNIQUE) — Chave da configuração (padrão: `'global_settings'`)
   * `value` (TEXT) — JSON contendo credenciais e parâmetros:
     * `smtp`: Servidor, porta, usuário, senha e remetente
     * `api_keys`: Credenciais do GestãoClick, caminho base dos YAMLs e flag de auto-sync
     * `inlabs`: Usuário e senha da Imprensa Nacional
     * `google_sheets`: URL da planilha, JSON de credenciais da Service Account, intervalo e mapeamento de colunas

7. **`email_templates` (`EmailTemplate`)**
   * `id` (INTEGER, PK)
   * `name` (VARCHAR(100)) — Nome do modelo (ex: `Padrão Registrale`)
   * `subject` (VARCHAR(200)) — Assunto padrão do e-mail
   * `body_html` (TEXT) — Estrutura HTML do e-mail com variáveis dinâmicas
   * `created_at` / `updated_at` (DATETIME)

---

## ⚙️ 4. Processamento Assíncrono e Threads em Segundo Plano

Para garantir alta performance e tempo de resposta instantâneo na interface web, o Dashboard utiliza threads de segundo plano (daemons) que são inicializadas na subida da aplicação (`create_app`):

### 1. Mentions Watcher (`start_mentions_watcher()`)
* Monitora o diretório de dados em busca de novos resultados gerados pelas tarefas de busca do Airflow.
* Ao identificar novas detecções, extrai as informações estruturadas (data, empresa, CNPJ, seção, trecho limpo e link da publicação), insere de forma atômica no banco SQLite (`Mention`) e registra o evento em `SyncHistory`.
* Permite que o dashboard exiba alertas sonoros e notificações em tempo real sem precisar reiniciar a aplicação.

### 2. Google Sheets Auto-Sync Scheduler (`GoogleSheetsScheduler`)
* Thread daemon dedicada que verifica a cada 60 segundos se o recurso de sincronização automática com o Google Sheets está ativo nas configurações (`settings.google_sheets.auto_sync`).
* Caso o intervalo configurado (ex: a cada 15, 30, 60 minutos ou 24 horas) tenha sido atingido, conecta-se de forma segura à API v4 do Google Sheets usando a Conta de Serviço, sincroniza novos CNPJs no banco e atualiza os arquivos YAML de busca.

### 3. Limpeza de DAGs Órfãs (`cleanup_orphaned_temp_dags()`)
* Função executada na inicialização da aplicação para realizar a manutenção do ambiente.
* Responsável por identificar e remover arquivos YAML temporários residuais e desregistrar DAGs órfãs do Airflow, mantendo o ambiente de execução limpo e consistente.
