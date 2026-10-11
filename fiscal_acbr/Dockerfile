# Comunicador ACBrLib do StarChef (docs/FISCAL_ACBRLIB.md).
#
# Debian, e não Alpine: a libacbrnfe64.so é compilada contra a glibc. A lib NÃO
# vem no repositório: é montada em /app/libs ou embutida pela Action em /opt/acbr.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/app/libs:/opt/acbr \
    ACBR_LIB_PATH=/app/libs/libacbrnfe64.so \
    ACBR_CONFIG=/app/config/ACBrLib.ini \
    TZ=America/Sao_Paulo

WORKDIR /app

# libxml2 + OpenSSL: assinatura e validação; fontconfig/fontes: impressão do DANFE.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 openssl ca-certificates libfontconfig1 fontconfig fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY config/ ./config/

# A lib EMBUTIDA, quando a Action a baixou (Secret ACBRLIB_SO_URL): sem ela a
# pasta só tem o LEIAME e a loja monta a sua em /app/libs, como antes.
COPY embutida/ /opt/acbr/

EXPOSE 8001

# UM worker: a ACBrLib não é reentrante para o mesmo handle (`app/acbrlib.py`).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
