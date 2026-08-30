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
* `--max-requests 200`: Reciclagem automática do worker a cada 200 requisições para evitar vazamentos de memória.
* `--max-requests-jitter 30`: Jitter aleatório para evitar que múltiplos workers reiniciem no mesmo instante.
* `--timeout 120`: Timeout de 120 segundos para operações de sincronização em massa.

---

## 🧪 4. Execução dos Testes Automatizados

A suíte de testes do dashboard possui **84 testes** cobrindo:
- Autenticação e sessão
- CRUD de empresas (com validação de CNPJ e duplicatas)
- Templates de e-mail (CRUD e proteção de templates padrão)
- Limpeza de dados (com controle de permissão master)
- Busca e autocomplete de empresas
- Exportação Excel e PDF corporativo diagramado
- Verificação de datas (feriados, janela 120 dias INLABS)
- Disparo individual e mensal de rotinas
- Status e configuração da rotina principal
- Política de retenção INLABS (LRU com proteção de datas)
- Limpeza de DAGs temporárias
- Padronização INLABS em novas rotinas
- Normalização e matching flexível de CNPJ com e sem pontuação

```bash
# Execução completa da suíte de testes do Dashboard:
python -m pytest rodou_dashboard/tests/ -v

# Execução completa dos testes do Core Ro-DOU (Airflow):
pytest tests/ -v
```

---

## 🛠️ 5. Scripts Automatizados no Windows (`.bat`)

O projeto conta com scripts para simplificar o ciclo de vida completo da aplicação no Windows:

| Script | Finalidade e Comportamento |
| :--- | :--- |
| **`instalar.bat`** | Cria `.env`, pastas de logs/dados, sobe os containers Docker (`docker compose up -d --build`), inicializa o Airflow/Postgres e abre o painel no navegador (`http://localhost:5000`). |
| **`atualizar.bat`** | Atualizador rápido: obtém os commits mais recentes (`git pull origin main`) e recompila/reinicia os containers (`docker compose up -d --build`). |
| **`desinstalar.bat`** | Desinstalador interativo com 2 modos:<br>• **Opção 1 (Desinstalação Completa):** Para e remove containers, volumes, redes, imagens Docker e **exclui todos os arquivos e a própria pasta do projeto** do computador.<br>• **Opção 2 (Limpeza de Dados):** Para containers e limpa os dados locais (`data/`, `mnt/`), logs e sessões, mantendo o código para reinstalação. |

---

## 🛡️ 6. Backup e Manutenção do Banco SQLite e PostgreSQL

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

---

## ⚙️ 7. Configuração Inicial Obrigatória

No primeiro deploy, o administrador deve realizar as seguintes configurações iniciais obrigatórias (exibidas via banner de alerta amarelo na tela inicial do dashboard):

1. **Rotina Principal**: E-mails de destino, assunto e agendamento via modal na tela inicial.
2. **Servidor SMTP**: Configurado dentro do mesmo modal ou na aba de configurações.
3. **Credenciais INLABS**: Usuário e senha do portal da Imprensa Nacional.
