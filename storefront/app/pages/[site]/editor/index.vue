<script setup lang="ts">
/**
 * `/{slug}/editor/` — edita a home do site.
 *
 * Sem id de página no endereço: o caminho comum é "quero mexer no meu site", e
 * obrigar a decorar um UUID para isso seria hostil. A home é resolvida depois
 * do login, a partir do site que o servidor confirmou ser do usuário — nunca a
 * partir do slug cru da URL.
 *
 * `ssr: false` porque o GrapesJS precisa de DOM e a sessão vive em cookie do
 * navegador. Isolar o editor em rota própria também é o que mantém o bundle
 * público limpo: o código do builder só é baixado por quem abre esta URL.
 */
import { fetchSitePages } from '~~/services/api/builder-pages'

definePageMeta({ ssr: false, layout: false })

const { slug: siteSlug } = useStorefrontTenant()
const { site } = useStorefrontAuth()

const pageId = ref('')
const failure = ref('')

async function resolveHomePage(siteId: string) {
  failure.value = ''
  try {
    // `fetchSitePages` já devolve a lista ordenada, com a home primeiro.
    const pages = await fetchSitePages(siteId)
    const home = pages.find((page) => page.is_home) ?? pages[0]
    if (!home) {
      failure.value = 'Este site ainda não tem nenhuma página.'
      return
    }
    pageId.value = home.id
  } catch {
    failure.value = 'Não foi possível carregar as páginas do site.'
  }
}

// Só depois que a porta abriu: `site` é o registro que o servidor confirmou.
watch(site, (value) => {
  if (value) resolveHomePage(value.id)
}, { immediate: true })

useHead({ title: 'Editor do cardápio' })
</script>

<template>
  <EditorAuthGate :site-slug="siteSlug">
    <p v-if="failure" class="sf-gate__hint" style="margin: 48px auto; max-width: 520px">{{ failure }}</p>
    <StorefrontBuilder v-else-if="pageId" :page-id="pageId" />
    <p v-else class="sf-gate__hint" style="margin: 48px auto; max-width: 520px">Abrindo o editor…</p>
  </EditorAuthGate>
</template>
