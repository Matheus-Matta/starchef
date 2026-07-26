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
COPY requirements /app/requirements
RUN pip install -r requirements/${REQUIREMENTS}.txt

COPY . /app

# Usuário não-root (uid 1000) para o runtime de produção. Não trocamos o USER
# aqui para não quebrar o dev (bind-mount + sqlite gravável); o compose de prod
# roda com `user: "1000:1000"`.
RUN adduser --disabled-password --gecos "" --uid 1000 appuser \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R appuser:appuser /app

EXPOSE 8000
