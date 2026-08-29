![banner](docs/img/banner.png)

# Registrale-DOU & Ro-DOU Dashboard

[![CI Tests](https://github.com/gestaogovbr/Ro-dou/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/gestaogovbr/Ro-dou/actions/workflows/ci-tests.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-2.2+-black.svg)](https://flask.palletsprojects.com/)
[![Airflow 2.10](https://img.shields.io/badge/airflow-2.10-red.svg)](https://airflow.apache.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

O **Registrale-DOU** é uma solução corporativa de alta performance para monitoramento automatizado, auditoria e *clipping* contínuo de publicações no **Diário Oficial da União (DOU - Seções 1, 2 e 3)** e em Diários Oficiais Municipais (via Querido Diário).

O projeto é um **fork customizado do [Ro-DOU](https://gestaogovbr.github.io/Ro-dou/)** (Ministério da Gestão e da Inovação - MGI), especialmente adaptado para as operações da **Registrale**, integrando a base de clientes do ERP comercial, planilhas colaborativas do Google Drive, relatórios corporativos executivos e disparo de notificações inteligentes.

---

## 🌟 Principais Recursos & Diferenciais da Registrale

* 🔄 **Sincronização com ERP GestãoClick:** Consumo automático da API de clientes com normalização de CNPJs e particionamento inteligente em blocos de até 150 empresas para execução paralela de alta velocidade no Airflow.
* 📊 **Integração com Google Sheets (API v4):** Sincronização segura com planilhas privadas via Conta de Serviço (*Service Account*), suporte a orientações por Linhas ou Colunas, mapeamento de cabeçalhos e agendamento automático (*background scheduler*).
* 🖥️ **Ro-DOU Dashboard:** Painel web moderno, reativo e responsivo construído com Alpine.js, Tailwind CSS e Lucide Icons, com suporte completo a **Modo Escuro (*Dark Mode*)** e Modo Claro.
* 📱 **Suporte a PWA (Progressive Web App):** Instale o painel como aplicativo nativo no Windows/macOS/Linux diretamente via Google Chrome ou Microsoft Edge (janela independente sem barra de navegação).
* 📢 **Feed em Tempo Real de Menções:** Detecção instantânea de publicações com badges por Seção do DOU, destaques no texto original, alertas sonoros e links diretos para a Imprensa Nacional (`in.gov.br`).
* 📑 **Central de Relatórios Executivos:** Exportação em lote para **Microsoft Excel (.xlsx)** formatado e **Adobe PDF Diagramado** com identidade visual oficial da Registrale, além de disparo por e-mail.
* 📧 **Templates Dinâmicos de E-mail:** Editor de templates HTML com preview em tempo real e tags dinâmicas (`{empresa}`, `{cnpj}`, `{secao}`, `{data}`, `{trecho}`, `{link}`).
* 🏛️ **Auditoria Histórica & Conexão INLABS:** Conexão nativa ao PostgreSQL do INLABS (`pg8000`), auditoria de lacunas e download sob demanda de matérias para buscas mensais e retroativas.
* 📖 **Manual do Usuário Integrado:** Guia prático de utilização passo a passo integrado diretamente na barra lateral da aplicação e disponível em [`MANUAL.md`](MANUAL.md).

---

## 🏛️ Arquitetura do Sistema

```
                          ┌──────────────────────────────────────────────┐
                          │               Usuário / Browser              │
                          │   (Alpine.js + Tailwind CSS + Lucide Icons)  │
                          └──────────────────────┬───────────────────────┘
                                                 │ HTTP / REST API (Port 5000)
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Ro-DOU Dashboard (Flask + Gunicorn)                                                           │
│  • Gestão de Empresas (GestãoClick API + Google Sheets API v4 + Cadastro Manual)               │
│  • Particionamento Dinâmico de YAMLs (Pesquisa_cnpj_part_*.yaml / Pesquisa_cnpj_sync.yaml)     │
│  • Central de Relatórios Executivos (PDF Diagramado via ReportLab + Excel via OpenPyXL)        │
│  • Notificações por E-mail (SMTP) com Templates Customizáveis HTML                              │
│  • Manual do Usuário Integrado na Sidebar                                                      │
│  • SQLite (/data/database.db) em modo WAL + Background Workers (Watcher & Scheduler)           │
└───────────────────────────────────────┬────────────────────────────────────────────────────────┘
                                        │ Orquestração via REST API (Port 8080)
                                        ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────┐
│  Ro-DOU Core & Airflow Engine                                                                  │
│  • Airflow Webserver & Scheduler (DAGs de Busca Diária, Retroativa e Mensal)                  │
│  • Módulo INLABS: Download e Carga Histórica no PostgreSQL com Retenção de 120 dias            │
│  • Indexador OpenSearch para buscas textuais rápidas                                           │
│  • Notificadores: E-mail (SMTP), Discord, Slack, Webhooks e IA Generativa                     │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Estrutura do Repositório

```text
Registrale-dou/
├── MANUAL.md                     # Manual Completo e Prático de Utilização do Sistema
├── README.md                     # Documentação de Apresentação e Guia Rápido
├── docker-compose.yml            # Orquestração dos containers (Airflow, Postgres, Dashboard, etc.)
├── dag_confs/                    # Arquivos YAML de configuração de DAGs e blocos de busca
├── data/                         # Volume persistente do banco SQLite e arquivos .env
├── docs/                         # Documentação pública do projeto core
├── rodou_dashboard/              # Módulo da Aplicação Web do Dashboard
│   ├── app/                      # Backend Flask (Rotas, Modelos e Serviços)
│   │   ├── routes/               # Blueprints (Auth, Empresas, Rotinas, Exportações, Admin, etc.)
│   │   ├── services/             # Regras de negócio (Google Sheets, GestãoClick, DAGs, Menções)
│   │   └── models.py             # Modelos SQLAlchemy (User, Company, Mention, Settings, etc.)
│   ├── docs/                     # Documentações técnicas e manuais oficiais
│   ├── templates/                # Templates HTML (index.html, login.html)
│   ├── tests/                    # Suíte de testes automatizados com Pytest
│   └── requirements.txt          # Dependências Python do dashboard
└── src/                          # Módulos centrais de busca, download e notificação do Ro-DOU
```

---

## 🚀 Como Executar o Projeto (Instalação em 1 Comando)

### Pré-requisitos
* [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado e em execução.
* [Make](https://www.gnu.org/software/make/) (nativo no Linux/macOS, via WSL ou Git Bash / Chocolatey / Scoop no Windows).
* Git.

---

### ⚡ Instalação Rápida

O projeto está 100% preparado para subir todo o ambiente (Dashboard, Airflow, PostgreSQL, OpenSearch, SMTP e conexões) automaticamente:

#### No Windows (Script Automatizado `.bat`):
```cmd
# 1. Clonar o repositório
git clone https://github.com/Yaddz/Registrale-dou.git
cd Registrale-dou

# 2. Executar o instalador (ou dê 2 cliques no arquivo instalar.bat)
.\instalar.bat
```

#### No Linux / macOS / WSL (`make run`):
```bash
# 1. Clonar o repositório
git clone https://github.com/Yaddz/Registrale-dou.git
cd Registrale-dou

# 2. Executar a inicialização completa
make run
```

> **O que a inicialização faz automaticamente por você:**
> 1. Cria o arquivo `.env` a partir de `.env.example` (se ainda não existir).
> 2. Cria todos os diretórios de logs, dados e volumes necessários.
> 3. Constrói e inicializa todos os containers Docker (`docker compose`).
> 4. Aguarda a inicialização do Airflow Webserver.
> 5. Cria as variáveis padrão do Airflow (`termos_exemplo_variavel`, `email_admin`, `path_tmp`).
> 6. Inicializa o schema do banco PostgreSQL (`inlabs`).
> 7. Configura as conexões do Airflow (`inlabs_db` e `inlabs_portal`).
> 8. Ativa a DAG principal de carga do INLABS (`ro-dou_inlabs_load_pg`).
> 9. Abre automaticamente o Dashboard no seu navegador.

---

### 📱 Como Instalar como Aplicativo Desktop (PWA)

O Dashboard possui suporte nativo a **PWA (Progressive Web App)**:

1. Acesse o painel em `http://localhost:5000` pelo **Google Chrome** ou **Microsoft Edge**.
2. Na barra de endereços, clique no ícone **⊕ (Instalar Registrale)** ou vá em *Menu (três pontos) > Apps > Instalar Registrale*.
3. O Dashboard será instalado como um aplicativo independente no seu computador, com atalho na Área de Trabalho/Menu Iniciar e abrindo em janela dedicada sem barras de navegador.

---

### 🌐 Endereços e Credenciais de Acesso:

* **Ro-DOU Dashboard:** [http://localhost:5000](http://localhost:5000)
  * **Usuário:** `admin` | **Senha:** `admin`
* **Apache Airflow:** [http://localhost:8080](http://localhost:8080)
  * **Usuário:** `airflow` | **Senha:** `airflow`
* **Webmail de Testes (smtp4dev):** [http://localhost:5001](http://localhost:5001)
* **OpenSearch API:** [http://localhost:9200](http://localhost:9200)

---

### 🛠️ Comandos Úteis do Makefile

| Comando | Ação |
| :--- | :--- |
| `make run` | Executa o setup completo inicial e sobe todos os serviços. |
| `make up` | Inicia os containers existentes em segundo plano. |
| `make down` | Para todos os containers do projeto. |
| `make logs` | Exibe os logs unificados de todos os serviços em tempo real. |
| `make tests` | Executa a suíte de testes dentro do container. |
| `make clean` | Para os containers e limpa dados temporários e logs. |
| `make clean-install` | Limpa o ambiente e refaz o `make run` do zero. |

---

### Opção 2: Execução Local do Dashboard (Desenvolvimento)

```bash
cd rodou_dashboard

# 1. Criar e ativar o ambiente virtual:
python -m venv venv
# No Windows:
.\venv\Scripts\activate
# No Linux/macOS:
source venv/bin/activate

# 2. Instalar dependências:
pip install -r requirements.txt

# 3. Executar o servidor Flask:
python -m flask run --host=0.0.0.0 --port=5000
```
O painel estará acessível em: `http://localhost:5000`.

---

## 🧪 Testes Automatizados

O repositório conta com uma suíte abrangente de testes cobrindo autenticação, rotas de API, sincronização com ERP/Google Sheets, templates e exportações:

```bash
# Executar os testes do Dashboard:
python -m pytest rodou_dashboard/tests -v

# Executar os testes do Core Ro-DOU:
python -m pytest tests/ -v
```

---

## 📚 Documentação e Manuais

* 📖 [**Manual do Usuário (`MANUAL.md`)**](MANUAL.md) — Guia prático de utilização, criação de rotinas, parametrizações e FAQ.
* 🏛️ [**01. Visão Geral e Arquitetura**](rodou_dashboard/docs/01_visao_geral_e_arquitetura.md)
* ⚙️ [**02. Guia de Funcionalidades do Painel**](rodou_dashboard/docs/02_guia_de_funcionalidades.md)
* 🔗 [**03. Integrações do Sistema (GestãoClick, Google Sheets, INLABS, SMTP)**](rodou_dashboard/docs/03_integracoes.md)
* 📡 [**04. Referência Completa da API REST**](rodou_dashboard/docs/04_referencia_da_api.md)
* 🛠️ [**05. Guia Operacional, Configuração e Deploy**](rodou_dashboard/docs/05_guia_operacional_e_deploy.md)

---

## 🤝 Créditos e Origem

O **Registrale-DOU** é baseado no projeto de código aberto **[Ro-DOU](https://gestaogovbr.github.io/Ro-dou/)**, desenvolvido e mantido pela Secretaria de Gestão e Inovação do **Ministério da Gestão e da Inovação em Serviços Públicos (MGI)**.

Agradecemos à equipe do projeto Ro-DOU e à comunidade open-source pela iniciativa de democratizar o acesso e o monitoramento dos Diários Oficiais no Brasil.
