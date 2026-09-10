import tailwindcss from '@tailwindcss/vite'

// A regra que este arquivo protege: o GrapesJS nunca entra no bundle público.
// Ele é importado dinamicamente, e só dentro de componentes `.client.vue` das
// rotas de editor — quem abre o cardápio no celular não baixa um editor visual
// de 1 MB para ver o preço de uma pizza.
export default defineNuxtConfig({
  compatibilityDate: '2025-01-01',
  devtools: { enabled: true },

  modules: ['@pinia/nuxt'],

  components: [
    // `global: true` nos blocos do renderer: eles são resolvidos por NOME, em
    // tempo de execução (`resolveComponent(name)` no `SfNode`), a partir do
    // tipo salvo no editor. A auto-importação normal do Nuxt é estática — ela
    // só inclui o componente que aparece escrito em algum template, então os
    // blocos chegariam ao navegador como tag desconhecida e a página sairia
    // vazia. Registrá-los globalmente é o que faz o mapa de tipos funcionar.
    { path: '~/components/renderer/blocks', pathPrefix: false, global: true },
    // Sem prefixo de caminho no resto: `renderer/SfNode.vue` vira `<SfNode>`,
    // e não `<RendererSfNode>`.
    { path: '~/components', pathPrefix: false },
  ],

  css: [
    '~/assets/css/tokens.css',
    '~/assets/css/storefront.css',
  ],

  vite: {
    plugins: [tailwindcss()],
  },

  runtimeConfig: {
    public: {
      // URL do Django. No dev aponta para o backend local; em produção, para o
      // domínio da API. O renderer público usa só as rotas /api/v1/public/**;
      // o editor usa /api/v1/storefront/** com o cookie `sf_*`.
      //
      // É o ÚNICO valor de ambiente que sobra: qual restaurante servir vem do
      // primeiro segmento da URL (`/burger/`), não de configuração. Uma imagem
      // serve todas as lojas — antes, `STOREFRONT_SITE_SLUG` era lido em tempo
      // de build e ficava congelado no bundle, então trocar de loja exigia
      // recompilar.
      apiBase: process.env.STOREFRONT_API_BASE || 'http://localhost:8000',
    },
  },

  router: {
    options: {
      // `/burger` e `/burger/` são o MESMO endereço. Com `strict`, a barra final
      // daria 404 — e ela aparece o tempo todo: em link copiado, em QR Code, no
      // autocomplete do navegador.
      strict: false,
    },
  },

  nitro: {
    compressPublicAssets: true,
  },

  app: {
    head: {
      htmlAttrs: { lang: 'pt-BR' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      ],
    },
  },

  typescript: {
    strict: true,
  },
})
