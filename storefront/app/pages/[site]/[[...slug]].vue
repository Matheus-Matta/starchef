<script setup lang="ts">
/**
 * O cardápio público de um restaurante.
 *
 * O primeiro segmento da URL é o SITE: `/burger/` abre a home do Burger,
 * `/burger/promocoes` abre a página `promocoes` dele, e `/pizzapalace/` é outro
 * restaurante servido pelo mesmo processo. O slug de `MenuSite` é único na
 * plataforma inteira, então ele basta para identificar a loja — sem DNS, sem
 * variável de ambiente por cliente.
 *
 * O catch-all é opcional (`[[...slug]]`) para que `/burger` e `/burger/` caiam
 * na home sem precisar de uma segunda rota. `editor` e `preview` são segmentos
 * estáticos e por isso vencem esta rota no ranking do vue-router.
 *
 * Renderiza no servidor de propósito: cardápio precisa aparecer rápido no 4G e
 * ser indexável pelo Google. O GrapesJS não entra neste bundle.
 */
import { fetchStorefront } from '~~/services/api/storefront'

const route = useRoute()
const { slug: siteSlug } = useStorefrontTenant()

const pageSlug = computed(() => {
  const parts = route.params.slug
  const segments = Array.isArray(parts) ? parts : parts ? [parts] : []
  return segments.filter(Boolean).join('/')
})

const { data: storefront, error } = await useAsyncData(
  () => `storefront:${siteSlug.value}:${pageSlug.value}`,
  () => fetchStorefront({ slug: siteSlug.value, page: pageSlug.value || undefined }),
  { watch: [pageSlug, siteSlug] },
)

// 404 do backend (site inexistente/inativo, ou página que não existe) vira 404
// de verdade aqui. Responder 200 com uma tela vazia faria o Google indexar
// endereço inexistente como se fosse página do restaurante.
if (error.value || !storefront.value) {
  throw createError({ statusCode: 404, statusMessage: 'Cardápio não encontrado', fatal: true })
}

if (pageSlug.value && storefront.value.page?.slug !== pageSlug.value) {
  throw createError({ statusCode: 404, statusMessage: 'Página não encontrada', fatal: true })
}

const seo = computed(() => ({
  ...(storefront.value?.site.seo ?? {}),
  ...(storefront.value?.page?.seo ?? {}),
}))

const title = computed(
  () => seo.value.title || storefront.value?.site.name || storefront.value?.restaurant.name || 'Cardápio',
)

useSeoMeta({
  title,
  description: () => seo.value.description || '',
  ogTitle: title,
  ogDescription: () => seo.value.description || '',
  ogImage: () => seo.value.og_image || storefront.value?.restaurant.logo || '',
  ogType: 'website',
  // `index: false` no SEO da página tira o cardápio do buscador — usado por
  // quem ainda está montando o site.
  robots: () => (seo.value.index === false ? 'noindex, nofollow' : 'index, follow'),
})

useHead(() => ({
  link: storefront.value?.site.theme?.faviconUrl
    ? [{ rel: 'icon', href: storefront.value.site.theme.faviconUrl }]
    : [],
}))
</script>

<template>
  <StorefrontRenderer v-if="storefront" :storefront="storefront" />
</template>
