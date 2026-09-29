# Imagem base por espelho publico, e o endereco e um ARG de proposito.
#
# Nenhum registro publico consultado SEM CREDENCIAL sobrevive para sempre: a
# cota nao e nossa, e do IP do runner, que o GitHub compartilha com todo mundo.
# O Docker Hub derrubou a v3.0.8 no limite de pull anonimo. Trocamos para o
# espelho da AWS, e ele derrubou a v3.0.58 com `429 toomanyrequests: Data limit
# exceeded` — outra cota, mesmo motivo.
#
# A licao nao foi "este espelho e melhor", foi parar de depender de UM. O CI
# pergunta a cada espelho qual esta de pe (`scripts/resolver_imagem_base.sh`) e
# passa o vencedor por `--build-arg`. O padrao abaixo mantem `docker build`
# manual funcionando igual, sem argumento nenhum.
ARG NODE_IMAGE=public.ecr.aws/docker/library/node:24-alpine
# Build de produção do frontend (Vue + Vite). Multi-stage: compila o SPA no
# Node e entrega os estáticos por um servidor estático simples (`serve`) — sem
# nginx. TLS e o proxy same-origin de /api e /ws são responsabilidade de um
# proxy reverso EXTERNO a este compose (nginx do host, Caddy, LB da nuvem
# etc.); esta imagem só serve os arquivos do build em HTTP puro.

# ── Stage 1: build ───────────────────────────────────────────────────────────
# jsdom 30/vitest 4 exigem Node >=22 (mesma razão do bump em .github/workflows/frontend.yml).
FROM ${NODE_IMAGE} AS build
WORKDIR /app

# Instala deps a partir do lockfile (build reproduzível).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# URL da API no bundle. Same-origin por padrão (/api/v1): o proxy externo deve
# servir o SPA e fazer proxy do /api na mesma origem — sem CORS e compatível
# com cookies SameSite=Lax.
RUN npm run build

# ── Stage 2: runtime (serve) ─────────────────────────────────────────────────
FROM ${NODE_IMAGE}
WORKDIR /app

# Pin de versão pelo mesmo motivo do `npm ci` no stage 1: build reproduzível.
RUN npm install -g serve@14.2.6

COPY --from=build /app/dist ./dist
COPY runtime-config.js.template ./runtime-config.js.template
COPY serve.json ./dist/serve.json
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

ENV API_URL=/api/v1
EXPOSE 8080
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["serve", "-s", "dist", "-l", "8080"]
