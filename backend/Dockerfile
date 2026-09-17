FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Seleciona o conjunto de dependências: development (default) ou production.
# O docker-compose.prod.yml passa REQUIREMENTS=production.
ARG REQUIREMENTS=development
# Opcional: hosts em que o pip confia sem verificar TLS (ex.: "pypi.org
# files.pythonhosted.org" atrás de proxy corporativo que intercepta HTTPS).
# Vazio por padrão — o build de produção não muda.
ARG PIP_TRUSTED_HOST=""
COPY requirements /app/requirements
RUN PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST}" pip install -r requirements/${REQUIREMENTS}.txt

COPY . /app

# Usuário não-root (uid 1000) para o runtime de produção. Não trocamos o USER
# aqui para não quebrar o dev (bind-mount + sqlite gravável); o compose de prod
# roda com `user: "1000:1000"`.
#
# `media/sync_tmp` e `sync` existem na IMAGEM de propósito: são onde a
# sincronização monta os pedaços de arquivo em trânsito (§16) e onde a
# matrícula grava as credenciais. Um volume montado sobre um caminho que NÃO
# existe na imagem nasce pertencendo ao root — e o processo roda como uid 1000,
# então toda gravação ali falha com "Permission denied". Criados aqui, o Docker
# copia o dono junto ao inicializar o volume.
RUN adduser --disabled-password --gecos "" --uid 1000 appuser \
    && mkdir -p /app/media/sync_tmp /app/staticfiles /app/sync \
    && chown -R appuser:appuser /app

EXPOSE 8000
