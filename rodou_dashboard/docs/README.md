# Documentação Oficial — Ro-DOU Dashboard

Bem-vindo à documentação oficial do **Ro-DOU Dashboard**, a plataforma central de monitoramento, gestão de empresas, automação de buscas no Diário Oficial da União (DOU) e disparo de relatórios e alertas da **Registrale**.

---

## 📚 Estrutura da Documentação

A documentação está dividida nos seguintes módulos:

1. [**01. Visão Geral e Arquitetura**](01_visao_geral_e_arquitetura.md)
   - Propósito do sistema e tecnologias utilizadas
   - Arquitetura geral e ciclo de dados
   - Modelos de banco de dados (SQLite e PostgreSQL INLABS)
   - Processamento assíncrono e threads em segundo plano

2. [**02. Guia de Funcionalidades do Painel**](02_guia_de_funcionalidades.md)
   - Painel Principal (Dashboard & KPIs em tempo real)
   - Gestão de Empresas Monitoradas (Importação, Edição, Busca)
   - Gerenciador de Rotinas de Busca (Diárias, Mensais, Personalizadas)
   - Central de Relatórios (Filtros avançados, Exportação Excel/PDF, E-mails)
   - Configurações do Sistema, Gestão de Usuários e Níveis de Acesso
   - Templates de E-mail Dinâmicos
   - Limpeza e Manutenção de Dados
   - Monitoramento do Armazenamento INLABS

3. [**03. Integrações do Sistema**](03_integracoes.md)
   - **GestãoClick API**: Sincronização automática de clientes do ERP
   - **Google Sheets API v4**: Integração segura via Service Account com planilhas privadas
   - **INLABS / Imprensa Nacional**: Conexão com banco PostgreSQL histórico de matérias do DOU
   - **Servidor SMTP**: Envio de alertas de detecção e relatórios corporativos

4. [**04. Referência Completa da API REST**](04_referencia_da_api.md)
   - Catálogo completo de endpoints
   - Autenticação e controle de sessão
   - Estrutura de requisição (Payloads) e respostas (JSON)

5. [**05. Guia Operacional, Configuração e Deploy**](05_guia_operacional_e_deploy.md)
   - Requisitos e variáveis de ambiente (`.env`)
   - Execução local para desenvolvimento
   - Deploy com Docker e Gunicorn
   - Execução dos testes automatizados

---

## 🚀 Resumo Rápido

* **Backend:** Python 3.10+, Flask, SQLAlchemy, Gunicorn.
* **Frontend:** Alpine.js, Tailwind CSS (CDN), Lucide Icons.
* **Bancos de Dados:** SQLite (banco de aplicação local `/data/dashboard.db`) + PostgreSQL (banco INLABS `/data/dou_inlabs`).
* **Sincronização:** Airflow DAGs + Workers em background (Google Sheets Scheduler e Mentions Watcher).
