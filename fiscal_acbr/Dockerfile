# Comunicador ACBrLib do StarChef (docs/FISCAL_ACBRLIB.md).
#
# Debian, e não Alpine: a libacbrnfe64.so é compilada contra a glibc. A lib NÃO
# vem na imagem — é distribuída pelo Projeto ACBr e montada em /app/libs.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LD_LIBRARY_PATH=/app/libs \
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

EXPOSE 8001

# UM worker: a ACBrLib não é reentrante para o mesmo handle (`app/acbrlib.py`).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
