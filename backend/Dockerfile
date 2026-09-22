# Imagem base pelo espelho publico da AWS, e nao pelo Docker Hub.
#
# O Hub limita pull ANONIMO por IP, e os runners do GitHub compartilham IP.
# Quando a cota estoura, o build morre na linha 1 com um erro que nao parece
# cota — "failed to fetch oauth token: connection reset by peer" — antes mesmo
# de o Dockerfile ser lido. Foi o que derrubou o build da v3.0.8.
#
# `public.ecr.aws/docker/library/*` e o espelho oficial das imagens `library`
# do Hub: mesma imagem, mesmas tags, sem limite para pull anonimo e sem
# precisar guardar credencial do Docker Hub como secret.
FROM public.ecr.aws/docker/library/python:3.12-slim

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
# A VERSÃO DO BUILD, gravada na imagem.
#
# O nó a declara no HELLO e ela vira a ficha "esta loja está na versão X" no
# admin da nuvem. Enquanto dependia de uma variável no `.env` de cada loja, ela
# envelhecia em silêncio — e a ficha mentia sobre a única coisa que ela conta.
#
# Vazio no build local é o certo: só o CI, que constrói a partir da tag, sabe
# o número de verdade.
ARG APP_VERSION=""
ENV STARCHEF_APP_VERSION=${APP_VERSION}
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
    && chown -R appuser:appuser /app     && chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

# A rede de segurança das triggers entra por AQUI, e não pelo `command` de cada
# compose. Deixá-la no compose é confiar que toda instalação — de toda loja, de
# todo cliente — lembrou de escrever a mesma linha; a nuvem não lembrou, e duas
# tabelas da comanda ficaram sem captura sem ninguém ver.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
