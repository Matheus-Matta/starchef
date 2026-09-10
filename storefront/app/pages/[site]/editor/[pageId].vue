<script setup lang="ts">
/**
 * `/{slug}/editor/{pageId}` — edita uma página específica do site.
 *
 * Mesma porta de entrada da rota sem id; o que muda é só a página aberta. A
 * checagem que importa continua sendo do servidor: além do 403 da sessão por
 * slug, a própria API de páginas é escopada por tenant, então um id de página
 * de outro restaurante devolve 404 mesmo que alguém o descubra.
 */
definePageMeta({ ssr: false, layout: false })

const route = useRoute()
const { slug: siteSlug } = useStorefrontTenant()
const pageId = computed(() => String(route.params.pageId ?? ''))

useHead({ title: 'Editor do cardápio' })
</script>

<template>
  <EditorAuthGate :site-slug="siteSlug">
    <StorefrontBuilder v-if="pageId" :page-id="pageId" />
  </EditorAuthGate>
</template>
