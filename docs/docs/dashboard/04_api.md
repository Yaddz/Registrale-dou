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
* **Descrição:** Verifica se há dias sem matérias baixadas no INLABS para um determinado mês/ano.
* **Query Params:** `?month=8&year=2026`

### `POST /api/routines/download_missing_inlabs`
* **Descrição:** Dispara o download das matérias do INLABS para os dias ausentes identificados.

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

### `POST /api/routines/cleanup_temp`
* **Descrição:** Força a limpeza manual imediata de arquivos YAML temporários (`temp_*.yaml`), desregistra DAGs órfãs na API do Airflow e remove pastas de logs temporárias (com `force_all=True`).
* **Resposta de Sucesso (200):**
```json
{
  "status": "success",
  "message": "2 DAG(s) e arquivo(s) temporário(s) removido(s) com sucesso.",
  "cleaned_count": 2
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

### `POST /api/sync`
* **Descrição:** Dispara a sincronização manual de clientes com a API do GestãoClick em background.

### `POST /api/save_settings`
* **Descrição:** Salva as configurações globais do sistema (`Settings`).

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
