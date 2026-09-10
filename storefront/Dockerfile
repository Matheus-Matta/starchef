# Imagem do storefront (Nuxt em modo SSR, servido pelo Nitro).
#
# Multi-stage: o build precisa de todas as dependências (Nuxt, GrapesJS,
# Tailwind); o runtime precisa só do `.output`, que o Nitro gera já com as
# dependências de produção embutidas. A imagem final não carrega `node_modules`
# nem o código-fonte — é a diferença entre ~1 GB e ~200 MB, e menos superfície
# exposta em produção.

# ── build ─────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app

# Só o manifesto primeiro: enquanto as dependências não mudarem, o Docker
# reaproveita esta camada e o build pula o download inteiro.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY . .

# As variáveis de runtime NÃO entram aqui: o Nuxt lê `runtimeConfig` do
# ambiente no boot. Assim a mesma imagem serve dev, homologação e produção, e
# trocar a URL da API não obriga a reconstruir nada.
ENV NODE_ENV=production
RUN npm run build

# ── runtime ───────────────────────────────────────────────────────────────────
FROM node:22-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NITRO_HOST=0.0.0.0 \
    NITRO_PORT=3000

# Usuário sem privilégios: a imagem `node` já traz o usuário `node`.
COPY --from=build --chown=node:node /app/.output ./.output

USER node
EXPOSE 3000

# Healthcheck bate na raiz. Ela responde 404 de propósito (sem slug não há loja
# a servir), e é justamente isso que a torna um bom alvo: prova que o Nitro está
# de pé sem depender de nenhum restaurante existir nem do Django estar no ar. Só
# 5xx reprova — uma indisponibilidade do backend não deve reiniciar o container
# em laço.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"

CMD ["node", ".output/server/index.mjs"]
