# 04. Referência Completa da API REST

Todas as rotas da API do **Ro-DOU Dashboard** requerem que o usuário esteja autenticado via sessão HTTP (exceto rotas públicas de login).

---

## 🔐 1. Autenticação e Sessão

| Endpoint | Método | Descrição |
| :--- | :--- | :--- |
| `/login` | `GET`, `POST` | Exibe o formulário de login ou valida as credenciais (`username` e `password`). |
| `/logout` | `GET` | Encerra a sessão do usuário e redireciona para `/login`. |
| `/api/extend_session` | `POST` | Estende o tempo de vida da sessão ativa por mais 30 minutos. |

---

## 🏢 2. Gestão de Empresas (`companies_bp`)

### `GET /api/companies`
* **Descrição:** Retorna a lista completa de empresas cadastradas no banco de dados.
* **Resposta de Sucesso (200):**
```json
[
  {
    "id": 1,
    "nome": "EMPRESA EXEMPLO LTDA",
    "cnpj": "12.345.678/0001-90",
    "origem": "gestaoclick",
    "status": true,
    "created_at": "2026-08-20T10:00:00"
  }
]
```

### `POST /api/companies`
* **Descrição:** Cadastra manualmente uma nova empresa.
* **Payload (JSON):**
```json
{
  "nome": "NOVA EMPRESA LTDA",
  "cnpj": "98.765.432/0001-10",
  "status": true
}
```

### `PUT /api/companies/<int:id>`
* **Descrição:** Atualiza dados de uma empresa existente (nome e/ou status de monitoramento).
* **Payload (JSON):**
```json
{
  "nome": "EMPRESA ATUALIZADA LTDA",
  "status": false
}
```

### `DELETE /api/companies/<int:id>`
* **Descrição:** Remove permanentemente uma empresa da base e regrava os arquivos YAML de busca (requer perfil `master`).

### `GET /api/companies/search`
* **Descrição:** Busca rápida com resposta instantânea por nome ou CNPJ para preenchimento de rotinas.
* **Query Params:** `?q=termo_de_busca`

### `GET /api/sheets/cnpjs`
* **Descrição:** Lê e retorna a lista de CNPJs diretamente da planilha Google Sheets conectada.

### `GET /api/company_history/<path:cnpj>`
* **Descrição:** Retorna todas as menções históricas salvas no banco de dados para um determinado CNPJ.

### `POST /api/google_sheets/test`
* **Descrição:** Testa as credenciais e parâmetros da planilha Google Sheets sem salvar no banco.
* **Payload (JSON):**
```json
{
  "spreadsheet_url": "https://docs.google.com/spreadsheets/d/.../edit",
  "sheet_name": "Página1",
  "credentials_json": "{ ... }"
}
```

### `POST /api/google_sheets/sync`
* **Descrição:** Executa a sincronização da planilha Google Sheets para o banco SQLite e atualiza os YAMLs.

### `POST /api/companies/toggle_origin_monitoring`
* **Descrição:** Ativa ou desativa em lote o monitoramento (`status`) de todas as empresas de uma origem específica.
* **Payload (JSON):**
```json
{
  "origin": "gestaoclick",
  "active": true
}
```

### `POST /api/companies/unmonitor_by_origin`
* **Descrição:** Desmarca o monitoramento (`status=False`) de empresas pertencentes a origens específicas.
* **Payload (JSON):**
```json
{
  "origins": ["gestaoclick", "google_sheets"]
}
```

---

## ⚙️ 3. Rotinas e Execuções (`dags_bp`)

### `GET /api/routines`
* **Descrição:** Retorna a lista de rotinas de busca configuradas no sistema (rotinas do sistema e personalizadas).

### `POST /api/routines`
* **Descrição:** Cria ou atualiza uma rotina de busca personalizada.
* **Payload (JSON):**
```json
{
  "name": "Busca Licitações Saúde",
  "schedule": "0 8 * * *",
  "source": "DOU",
  "terms": ["termo 1", "termo 2"],
  "sections": ["SECAO_1", "SECAO_3"],
  "organs": ["ANVISA", "Ministério da Saúde"],
  "emails": ["alerta@empresa.com"],
  "active": true
}
```

### `POST /api/routines/toggle/<path:file>`
* **Descrição:** Ativa ou pausa uma rotina de busca.

### `DELETE /api/routines/<path:file>`
* **Descrição:** Exclui uma rotina personalizada.

### `POST /api/routines/trigger/<path:file>`
* **Descrição:** Dispara a execução imediata de uma rotina, opcionalmente com uma data específica.
* **Payload (JSON):**
```json
{
  "logical_date": "2026-08-15"
}
```

### `GET /api/routines/monthly_inlabs_check`
* **Descrição:** Verifica se há dias sem matérias baixadas no INLABS para um determinado mês/ano, segregando dias baixáveis (janela de 120 dias) e dias históricos (API DOU).
* **Query Params:** `?month=8&year=2026&routine=Pesquisa_cnpj.yaml`
* **Resposta de Sucesso (200):**
```json
{
  "status": "ok",
  "scenario": "mixed",
  "uses_inlabs": true,
  "total_weekdays": 21,
  "inlabs_count": 10,
  "missing_count": 11,
  "downloadable_count": 5,
  "api_dou_count": 6,
  "downloadable_inlabs_days": ["2026-08-01"],
  "api_dou_days": ["2026-08-15"]
}
```
* **Valores possíveis de `scenario`:**
  * `"complete"`: Todos os dias do mês já estão no banco de dados.
  * `"download_only"`: Dias faltantes estão todos dentro da janela de 120 dias do INLABS.
  * `"all_api_dou"`: Todos os dias faltantes estão fora da janela de 120 dias (pesquisa total via API DOU).
  * `"mixed"`: Cenário misto com dias baixáveis no INLABS e dias históricos via API DOU.

### `POST /api/routines/download_missing_inlabs`
* **Descrição:** Dispara o download das matérias do INLABS para os dias ausentes identificados dentro da janela de 120 dias.

### `POST /api/routines/trigger_monthly`
* **Descrição:** Dispara a execução das buscas para todos os dias do mês selecionado.
* **Payload (JSON):**
```json
{
  "month": 8,
  "year": 2026,
  "routines": ["Pesquisa_cnpj.yaml"],
  "mode": "download_and_search"
}
```
* **Modos suportados (`mode`):**
  * `"full"`: Executa dias INLABS e pesquisa dias faltantes via API DOU.
  * `"download_and_search"`: Baixa dias faltantes na janela de 120 dias no INLABS e busca dias históricos via API DOU.
  * `"inlabs_only"`: Executa buscas somente para os dias com dados já disponíveis no PostgreSQL.
  * `"api_dou_only"`: Executa todas as buscas diretamente via API Oficial do DOU (para meses fora da janela de 120 dias).

### `GET /api/system/integrations_status` / `GET /api/system/main_dag_status`
* **Descrição:** Retorna o diagnóstico completo de todas as 4 integrações do sistema para o Assistente de Configuração (Setup Wizard) e o alerta do painel.
* **Resposta de Sucesso (200):**
```json
{
  "status": "ok",
  "is_configured": true,
  "all_configured": false,
  "pending_count": 1,
  "next_pending": {
    "id": "google_sheets",
    "name": "Google Sheets",
    "title": "Planilha Google Sheets",
    "description": "Conecte a planilha com credenciais de serviço para sincronização automática de empresas."
  },
  "integrations": [
    {
      "id": "main_dag",
      "name": "Rotina Principal",
      "is_configured": true,
      "missing_fields": []
    },
    {
      "id": "smtp",
      "name": "Servidor SMTP",
      "is_configured": true,
      "missing_fields": []
    },
    {
      "id": "google_sheets",
      "name": "Google Sheets",
      "is_configured": false,
      "missing_fields": ["credentials_json"]
    },
    {
      "id": "inlabs",
      "name": "Acesso INLABS",
      "is_configured": true,
      "missing_fields": []
    }
  ],
  "main_dag": {
    "emails": ["alerta@empresa.com"],
    "subject": "[Registrale] Relatório Diário",
    "schedule": "0 8 * * MON-FRI",
    "is_configured": true
  },
  "smtp_configured": true,
  "smtp": {
    "server": "smtp.gmail.com",
    "port": "587",
    "user": "alerta@empresa.com",
    "from_email": "alerta@empresa.com",
    "has_password": true
  }
}
```

### `POST /api/system/configure_main_dag`
* **Descrição:** Configura atomicamente os e-mails de destino, assunto, agendamento (cron) da rotina principal e servidor SMTP. Requer perfil `master`.
* **Payload (JSON):**
```json
{
  "emails": ["email1@empresa.com", "diretoria@empresa.com"],
  "subject": "[Registrale] Relatório Diário de Publicações do DOU",
  "schedule": "0 8 * * MON-FRI",
  "active": true,
  "smtp": {
    "server": "smtp.gmail.com",
    "port": "587",
    "user": "seu-email@gmail.com",
    "password": "app-password-16-chars",
    "from_email": "notificacoes@empresa.com"
  }
}
```
* **Validações:**
  * Pelo menos um e-mail de destino é obrigatório.
  * Cada e-mail é validado contra regex `^[\w\.-]+@[\w\.-]+\.\w+$`.
  * Se a senha SMTP não for informada, a senha anterior é preservada.
  * Senhas de App do Gmail têm espaços removidos automaticamente.
* **Resposta de Sucesso (200):**
```json
{
  "status": "success",
  "message": "Rotina principal configurada com sucesso!"
}
```

### `POST /api/routines/cleanup_temp`
* **Descrição:** Força a limpeza imediata de arquivos YAML temporários (`temp_*.yaml`) e DAGs órfãs do Airflow.
* **Resposta de Sucesso (200):**
```json
{
  "status": "ok",
  "message": "Limpeza executada."
}
```

---

## 📢 4. Menções Detectadas (`mentions_bp`)

### `GET /api/mentions`
* **Descrição:** Retorna todas as menções salvas no banco de dados, ordenadas da mais recente para a mais antiga.

### `DELETE /api/mentions`
* **Descrição:** Remove menções do banco de dados por lista de IDs ou por CNPJ.
* **Payload (JSON):**
```json
{
  "ids": [10, 11, 12]
}
```
*ou*
```json
{
  "cnpj": "12.345.678/0001-90"
}
```

---

## 📄 5. Exportações e Relatórios (`exports_bp`)

### `POST /api/export_pdf`
* **Descrição:** Gera e faz download de um relatório corporativo em PDF da listagem de empresas cadastradas (gera arquivo temporário isolado e thread-safe).
* **Payload (JSON):**
```json
{
  "companies": [ { ... } ]
}
```

### `POST /api/export_mentions_excel`
* **Descrição:** Gera e faz download de uma planilha Excel `.xlsx` corporativa com abas de dados e metadados de geração.
* **Payload (JSON):**
```json
{
  "mentions": [ { ... } ],
  "filters": { ... }
}
```

### `POST /api/export_mentions_pdf`
* **Descrição:** Gera e faz download de um relatório PDF diagramado contendo as publicações selecionadas com cabeçalho oficial e links para o DOU.

### `POST /api/send_email`
* **Descrição:** Dispara e-mail com relatório formatado para uma lista de destinatários.
* **Payload (JSON):**
```json
{
  "to_emails": ["cliente@exemplo.com"],
  "subject": "Relatório de Publicações no DOU",
  "body_html": "<p>Segue o relatório...</p>"
}
```

### `POST /api/test_smtp`
* **Descrição:** Testa o envio de e-mail usando as configurações SMTP atuais.
* **Payload (JSON):**
```json
{
  "test_email": "teste@empresa.com"
}
```

---

## 🛠️ 6. Administração e Sistema (`admin_bp`)

### `GET /api/status`
* **Descrição:** Retorna o status geral do painel, KPIs de menções, horários de sincronização e últimos eventos do histórico.

### `GET /api/settings`
* **Descrição:** Retorna as configurações globais consolidadas do sistema (`global_settings`). Requer perfil `master`.
* **Resposta de Sucesso (200):**
```json
{
  "status": "ok",
  "settings": {
    "smtp": {
      "server": "smtp.gmail.com",
      "port": "587",
      "user": "notificacoes@empresa.com",
      "from_email": "notificacoes@empresa.com"
    },
    "google_sheets": {
      "spreadsheet_url": "https://docs.google.com/spreadsheets/d/.../edit",
      "sheet_name": "Clientes",
      "auto_sync": true
    },
    "api_keys": {
      "gestaoclick_base_url": "https://api.gestaoclick.com/franquias"
    },
    "inlabs": {
      "user": "usuario_inlabs"
    }
  }
}
```

### `POST /api/save_settings`
* **Descrição:** Salva as configurações globais do sistema (`Settings`). Preserva senhas preexistentes quando o campo for enviado em branco, higieniza espaços em senhas de app do Gmail e sincroniza a conexão `smtp_default` no Airflow. Requer perfil `master`.

### `POST /api/sync`
* **Descrição:** Dispara a sincronização manual de clientes com a API do GestãoClick em background.

### `GET /api/users` / `POST /api/users` / `DELETE /api/users`
* **Descrição:** Gerencia os usuários internos do painel.

### `POST /api/admin/clear_data`
* **Descrição:** Executa a limpeza seletiva ou total do banco de dados.
* **Payload (JSON):**
```json
{
  "type": "inlabs_old"
}
```
* **Opções de `type`:**
  * `"all"`: Apaga todos os registros de empresas, menções e histórico.
  * `"inlabs_old"`: Remove publicações do INLABS com mais de **120 dias** no PostgreSQL.
  * `"history"`: Limpa a tabela de histórico de sincronização.
  * `"mentions"`: Apaga todas as menções salvas no painel.

### `GET /api/inlabs_stats`
* **Descrição:** Retorna o espaço utilizado pelo banco PostgreSQL do INLABS e a listagem de dias armazenados.

---

## 📝 7. Modelos de E-mail (`templates_bp`)

### `GET /api/templates`
* **Descrição:** Lista todos os modelos de e-mail cadastrados.

### `POST /api/templates`
* **Descrição:** Cria ou edita um modelo de e-mail.
* **Payload (JSON):**
```json
{
  "id": 1,
  "name": "Aviso Urgente DOU",
  "subject": "Identificamos uma publicação da {empresa}",
  "body_html": "<h1>Aviso</h1><p>CNPJ: {cnpj}</p><p>{trecho}</p>"
}
```

### `DELETE /api/templates/<int:id>`
* **Descrição:** Remove um modelo de e-mail personalizado (o modelo padrão do sistema é protegido contra exclusão).
