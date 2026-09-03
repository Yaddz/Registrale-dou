# 05. Guia Operacional, Configuração e Deploy

Este guia orienta como configurar, executar localmente, realizar o build Docker e manter o **Ro-DOU Dashboard** em ambiente de produção.

---

## ⚙️ 1. Variáveis de Ambiente (`.env`)

O sistema carrega automaticamente as variáveis definidas no arquivo `.env` localizado na raiz ou montado no volume `/data/.env`:

```ini
# --- Configurações da Aplicação Flask ---
FLASK_APP=app:create_app()
FLASK_ENV=production
SECRET_KEY=sua_chave_secreta_super_segura_aqui

# --- Diretório de Dados Persistentes ---
DATA_DIR=/data

# --- API GestãoClick ---
BASE_URL=https://api.gestaoclick.com/franquias
ACCESS_TOKEN=seu_access_token
SECRET_ACCESS_TOKEN=seu_secret_access_token
YAML_PATH=dag_confs/Pesquisa_cnpj_sync.yaml

# --- Banco Histórico INLABS (PostgreSQL) ---
INLABS_DB_HOST=postgres_inlabs
INLABS_DB_PORT=5432
INLABS_DB_NAME=dou_inlabs
INLABS_DB_USER=inlabs_user
INLABS_DB_PASSWORD=inlabs_password

# --- Servidor SMTP de Notificações ---
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu_email@registrale.com.br
SMTP_PASSWORD=sua_senha_ou_app_password
SMTP_FROM_EMAIL=notificacoes@registrale.com.br
```

---

## 💻 2. Execução Local para Desenvolvimento

### Passo 1: Criar e ativar o ambiente virtual (opcional)
```bash
python -m venv venv
# No Windows:
.\venv\Scripts\activate
# No Linux/macOS:
source venv/bin/activate
```

### Passo 2: Instalar as dependências
```bash
pip install -r requirements.txt
```

### Passo 3: Executar a aplicação com Flask
```bash
python -m flask run --host=0.0.0.0 --port=5000
```
O painel estará acessível em: `http://localhost:5000`

---

## 🐳 3. Deploy com Docker e Gunicorn

O arquivo `Dockerfile` já está otimizado para ambiente de produção com Python 3.10-slim e Gunicorn:

### Construir a Imagem Docker:
```bash
docker build -t registrale/rodou-dashboard:latest .
```

### Executar o Container:
```bash
docker run -d \
  --name rodou_dashboard \
  --restart unless-stopped \
  -p 5000:5000 \
  -v /caminho/no/host/data:/data \
  -v /caminho/no/host/dag_confs:/app/dag_confs \
  --env-file .env \
  registrale/rodou-dashboard:latest
```

### Parâmetros do Gunicorn configurados no Dockerfile:
* `-w 2`: 2 workers simultâneos para balanceamento de carga.
* `--max-requests 5000`: Reciclagem automática do worker a cada 5.000 requisições para evitar vazamentos de memória sem interromper pesquisas longas em background.
* `--max-requests-jitter 500`: Jitter aleatório para evitar que múltiplos workers reiniciem no mesmo instante.
* `--timeout 120`: Timeout de 120 segundos para operações de sincronização em massa.

---

## 🧪 4. Execução dos Testes Automatizados

A suíte de testes do dashboard utiliza `pytest` e cobre autenticação, APIs de empresas, rotinas, templates e integração com Google Sheets:

```bash
python -m pytest tests -v
```

Para rodar com relatório de warnings detalhados:
```bash
python -m pytest tests --disable-warnings
```

---

## 🛡️ 5. Backup e Manutenção do Banco SQLite

O banco SQLite `/data/dashboard.db` opera em modo WAL (*Write-Ahead Logging*).

### Procedimento Seguro de Backup:
Para realizar o backup do banco sem interromper a execução do painel:

```bash
# Utilizando o comando sqlite3 online backup
sqlite3 /data/dashboard.db ".backup '/data/backups/dashboard_backup_$(date +%Y%m%d_%H%M%S).db'"
```

---

## 🔧 6. Solução de Problemas Comuns (Troubleshooting)

### A. Erro ao conectar ao daemon do Docker no Windows:
```
unable to get image '...': error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/...": open //./pipe/dockerDesktopLinuxEngine: O sistema não pode encontrar o arquivo especificado.
```
* **Causa:** O aplicativo **Docker Desktop** não está aberto ou o serviço de virtualização WSL2 ainda não concluiu a inicialização no Windows.
* **Solução:**
  1. Abra o **Docker Desktop** pelo Menu Iniciar do Windows (`C:\Program Files\Docker\Docker\Docker Desktop.exe`).
  2. Aguarde o ícone do Docker na bandeja do sistema ficar verde (*"Engine running"*).
  3. Execute novamente o comando `docker compose up -d` ou `docker build`.
  4. Caso o Docker Desktop trave na inicialização, reinicie o subsistema WSL no PowerShell (como Administrador): `wsl --shutdown`.

### B. Conflito de Porta 5000:
* Se a porta `5000` estiver ocupada por outro serviço, inicie em uma porta alternativa mapeada:
```bash
docker run -d -p 5001:5000 ... registrale/rodou-dashboard:latest
```
ou em execução local:
```bash
python -m flask run --host=0.0.0.0 --port=5001
```

### C. Bloqueio de Concorrência no SQLite (*Database is locked*):
* O Ro-DOU Dashboard configura automaticamente os modos `WAL` e `busy_timeout=5000` na inicialização do Flask. Caso execute scripts externos de manutenção diretamente contra o arquivo `/data/dashboard.db`, certifique-se de não manter transações abertas em modo exclusivo.
