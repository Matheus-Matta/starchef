#!/usr/bin/env sh
# Sobe o StarChef da loja (Linux). Rode nesta pasta:
#   sh instalar.sh
#
# Mesmo roteiro do instalar.ps1: cria/completa o .env.local, gera os segredos,
# pergunta o IP, baixa as imagens e sobe. Rodar de novo é seguro — nada que já
# está preenchido é trocado (trocar a senha do banco depois quebraria o acesso).
set -eu
cd "$(dirname "$0")"

ENV_FILE=.env.local
compose() { docker compose --env-file "$ENV_FILE" -f docker-compose.local.yml "$@"; }

segredo() { head -c "$1" /dev/urandom | base64 | tr -d '+/=\n'; }
ler() { sed -n "s/^[[:space:]]*$1=//p" "${2:-$ENV_FILE}" | tail -n 1 | tr -d '\r'; }
gravar() {
  if grep -q "^[[:space:]]*$1=" "$ENV_FILE"; then
    # `|` como separador: segredo em base64 nunca tem `|` (removemos + / =).
    sed -i "s|^[[:space:]]*$1=.*|$1=$2|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
  fi
}
ip_da_loja() {
  hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)' | head -n 1
}

if ! docker info >/dev/null 2>&1; then
  echo "O Docker não está rodando (ou este usuário não pode usá-lo). Corrija e rode de novo." >&2
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  cp .env.local.example "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Criado $ENV_FILE a partir do exemplo."
fi

[ -n "$(ler STARCHEF_VERSION)" ] || gravar STARCHEF_VERSION "$(ler STARCHEF_VERSION .env.local.example)"
[ -n "$(ler DJANGO_SECRET_KEY)" ] || { gravar DJANGO_SECRET_KEY "$(segredo 48)"; echo "Gerada a chave do Django."; }
[ -n "$(ler POSTGRES_PASSWORD)" ] || { gravar POSTGRES_PASSWORD "$(segredo 24)"; echo "Gerada a senha do banco."; }
[ -n "$(ler SYNC_ENROLL_SECRET)" ] || gravar SYNC_ENROLL_SECRET "$(segredo 32)"

# Loja sem sincronização cria a conta pelo primeiro acesso, e ele exige token.
if [ "$(ler SYNC_ENABLED)" != "true" ] && [ -z "$(ler DJANGO_FIRST_ACCESS_TOKEN)" ]; then
  gravar DJANGO_FIRST_ACCESS_TOKEN "$(segredo 18)"
fi

atual="$(ler STORE_HOST)"
if [ -z "$atual" ] || [ "$atual" = "192.168.0.10" ]; then
  sugerido="$(ip_da_loja || true)"
  printf 'IP deste servidor na rede da loja [%s]: ' "$sugerido"
  read -r resposta || resposta=""
  resposta="${resposta:-$sugerido}"
  if [ -z "$resposta" ]; then
    echo "Não foi possível descobrir o IP. Preencha STORE_HOST no $ENV_FILE e rode de novo." >&2
    exit 1
  fi
  gravar STORE_HOST "$resposta"
fi

if [ "$(ler SYNC_ENABLED)" = "true" ] && [ -z "$(ler SYNC_AUTH_TOKEN)" ]; then
  for chave in SYNC_ACCOUNT_ID SYNC_ENROLL_USERNAME SYNC_ENROLL_PASSWORD; do
    if [ -z "$(ler "$chave")" ]; then
      echo "SYNC_ENABLED=true, mas $chave está vazio no $ENV_FILE. Preencha e rode de novo." >&2
      exit 1
    fi
  done
fi

compose config --quiet
compose pull
compose up -d

porta="$(ler HTTP_PORT)"; porta="${porta:-80}"
base="http://$(ler STORE_HOST)"; [ "$porta" = "80" ] || base="$base:$porta"
echo "Esperando o backend ficar pronto (a primeira subida aplica as migrations e leva alguns minutos)..."
i=0
while [ $i -lt 60 ]; do
  if curl -fsS "http://127.0.0.1:$porta/health/" >/dev/null 2>&1; then
    echo
    echo "StarChef no ar."
    echo "  Painel:       $base/"
    echo "  API do PDV:   $base/api/v1"
    echo "  Admin:        $base/admin/"
    if [ "$(ler SYNC_ENABLED)" != "true" ] && [ -n "$(ler DJANGO_FIRST_ACCESS_TOKEN)" ]; then
      echo "  Primeiro acesso: abra o Admin e use o token $(ler DJANGO_FIRST_ACCESS_TOKEN) para criar a conta e o administrador."
    fi
    exit 0
  fi
  i=$((i + 1)); sleep 10
done
echo "O backend não respondeu em 10 minutos. Veja: docker compose --env-file $ENV_FILE -f docker-compose.local.yml logs backend" >&2
exit 1
