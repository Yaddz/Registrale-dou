FROM python:3.10-slim

WORKDIR /app

# Instalar dependências de sistema para compilação se necessário (ex: psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependências unificadas
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY app/ app/
COPY templates/ templates/
COPY static/ static/

# Expõe a porta do Flask
EXPOSE 5000

# Comando para iniciar o Dashboard em produção usando Gunicorn com reciclagem estável de memória
CMD ["gunicorn", "-w", "2", "--max-requests", "5000", "--max-requests-jitter", "500", "--timeout", "120", "-b", "0.0.0.0:5000", "app:create_app()"]
