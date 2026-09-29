#!/usr/bin/env bash
# Escolhe de qual espelho publico a imagem base vem HOJE.
#
# O Dockerfile aponta para um registro so, e isso ja nos custou dois releases.
# O Docker Hub limita pull ANONIMO por IP e os runners do GitHub compartilham
# IP: foi o que derrubou a v3.0.8. Trocamos para o espelho da AWS, e a v3.0.58
# morreu no mesmo lugar por outro motivo — `public.ecr.aws` devolveu
# `429 toomanyrequests: Data limit exceeded`, que e a cota de TRAFEGO anonimo,
# tambem por IP compartilhado.
#
# A licao nao e "este espelho e melhor": e que qualquer registro publico
# consultado sem credencial vai estourar alguma cota mais cedo ou mais tarde,
# porque a cota nao e nossa, e do IP do runner. Entao o build para de depender
# de um: pergunta a cada espelho, na ordem, e usa o primeiro que responde.
#
#   scripts/resolver_imagem_base.sh python:3.12-slim
#   -> public.ecr.aws/docker/library/python:3.12-slim
#
# Todos servem a MESMA imagem oficial `library/<nome>` do Docker Hub, entao a
# escolha nao muda o que e construido — muda so por onde os bytes vem.
set -euo pipefail

IMAGEM="${1:?uso: resolver_imagem_base.sh <nome:tag>, por exemplo python:3.12-slim}"

# Ordem deliberada: o espelho da AWS primeiro porque ja era o nosso e continua
# sendo o mais rapido quando tem cota; o da Google depois, que e espelho do Hub
# e nao aplica o limite de pull anonimo dele; o Hub por ultimo, que e a origem
# de todos e o mais provavel de recusar.
ESPELHOS=(
  "public.ecr.aws/docker/library/${IMAGEM}"
  "mirror.gcr.io/library/${IMAGEM}"
  "docker.io/library/${IMAGEM}"
)

for candidato in "${ESPELHOS[@]}"; do
  # `imagetools inspect` le o manifesto sem baixar camada nenhuma. Uma cota
  # estourada reprova aqui do mesmo jeito que reprovaria no build — foi
  # exatamente num GET de manifesto que a v3.0.58 tomou o 429 —, entao a
  # pergunta e representativa e custa alguns kB.
  if docker buildx imagetools inspect "${candidato}" >/dev/null 2>&1; then
    echo "${candidato}"
    exit 0
  fi
  echo "espelho indisponivel, tentando o proximo: ${candidato}" >&2
done

echo "Nenhum espelho respondeu por ${IMAGEM}: ${ESPELHOS[*]}" >&2
echo "Os tres estao fora ou com cota estourada. Rode de novo em alguns minutos." >&2
exit 1
