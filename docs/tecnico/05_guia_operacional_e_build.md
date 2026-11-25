# 05. Guia Operacional, Configuração e Build

Este guia orienta como configurar, executar localmente, gerar o instalador Windows e manter o **Registrale-DOU**.

---

## ⚙️ 1. Variáveis de Ambiente (`.env`)

O sistema carrega opcionalmente variáveis definidas no `.env` do diretório de dados (`%LOCALAPPDATA%\Registrale` no Windows ou `REGISTRALE_DATA_DIR`):

```ini
# --- Diretório de Dados Persistentes (opcional) ---
# Padrão no Windows: %LOCALAPPDATA%\Registrale
REGISTRALE_DATA_DIR=

# --- Contingência INLABS (pdf | api | off) ---
REGISTRALE_INLABS_FALLBACK=pdf

# --- API GestãoClick (opcional; também configurável pelo painel) ---
BASE_URL=https://api.gestaoclick.com/franquias
ACCESS_TOKEN=seu_access_token
SECRET_ACCESS_TOKEN=seu_secret_access_token
```

---

## 💻 2. Execução Local para Desenvolvimento

Requer Python 3.11 e [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync --group dev
uv run registrale
```
O painel estará acessível em: `http://127.0.0.1:5000`

---

## 🖥️ 3. Execução Local e Empacotamento Windows

O painel roda em servidor WSGI **Waitress** (multi-thread em processo único) com agendador **APScheduler** e executor local (`LocalExecutor`).

### Execução em Desenvolvimento (`uv`)
```bash
uv sync --group dev
uv run registrale
```

### Build do Instalador Windows (`Inno Setup`)
```powershell
.\windows\build.ps1
```
O instalador (`dist/Registrale-Setup-<versão>.exe`) instala o Python 3.11 *embeddable* e o aplicativo em `%LOCALAPPDATA%\Programs\Registrale`, mantendo dados, logs e rotinas em `%LOCALAPPDATA%\Registrale`.

---

## 🧪 4. Execução dos Testes Automatizados

```bash
# Execução completa da suíte offline (núcleo + painel):
uv run pytest -m "not live" -q
```

---

## 🛠️ 5. Diretórios de Dados e Logs no Windows

| Conteúdo | Caminho padrão |
|---|---|
| Programa e launcher de bandeja | `%LOCALAPPDATA%\Programs\Registrale` |
| Banco SQLite (`database.db`), logs e rotinas YAML | `%LOCALAPPDATA%\Registrale` |
| PDFs integrais do DOU | `Documentos\Registrale\DOU` |

---

## 🛡️ 6. Backup e Solução de Problemas Comuns

O banco SQLite (`%LOCALAPPDATA%\Registrale\database.db`) opera em modo WAL (*Write-Ahead Logging*).

### Procedimento Seguro de Backup:
```bash
sqlite3 "%LOCALAPPDATA%\Registrale\database.db" ".backup database_backup.db"
```

### Conflito de Porta 5000:
Se a porta `5000` estiver ocupada por outro serviço, inicie em uma porta alternativa:
```bash
uv run registrale --port 5001
```

### Bloqueio de Concorrência no SQLite (*Database is locked*):
O painel configura automaticamente `WAL` e `busy_timeout=5000` na inicialização. Caso execute scripts externos diretamente contra `database.db`, não mantenha transações abertas em modo exclusivo.

---

## ⚙️ 7. Configuração Inicial Obrigatória

No primeiro deploy, o administrador deve realizar as seguintes configurações iniciais obrigatórias (exibidas via banner de alerta amarelo na tela inicial do dashboard):

1. **Rotina Principal**: E-mails de destino, assunto e agendamento via modal na tela inicial.
2. **Servidor SMTP**: Configurado dentro do mesmo modal ou na aba de configurações.
3. **Credenciais INLABS**: Usuário e senha do portal da Imprensa Nacional.
