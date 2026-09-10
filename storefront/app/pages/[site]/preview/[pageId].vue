<script setup lang="ts">
/**
 * `/{slug}/preview/{pageId}` — o rascunho, com o renderer de produção.
 *
 * O ponto é justamente esse: o preview NÃO usa o canvas do GrapesJS. Usa o
 * mesmo `StorefrontRenderer` que o cliente final vai ver, alimentado pelo
 * `draft_data`. Assim a diferença entre "como ficou no editor" e "como ficou no
 * ar" aparece antes de publicar, e não depois.
 *
 * Passa pela mesma porta do editor: o rascunho é conteúdo não publicado, e
 * mostrá-lo a quem não é do restaurante seria vazar a próxima campanha da casa.
 */
import { fetchDraftPreview } from '~~/services/api/builder-pages'
import type { StorefrontPayload } from '~~/types/storefront'

definePageMeta({ ssr: false, layout: false })

const route = useRoute()
const { slug: siteSlug } = useStorefrontTenant()
const { site } = useStorefrontAuth()

const pageSlug = computed(() => String(route.query.page ?? ''))
const storefront = ref<StorefrontPayload | null>(null)
const failure = ref('')

async function load(siteId: string) {
  failure.value = ''
  try {
    storefront.value = await fetchDraftPreview(siteId, pageSlug.value || undefined)
  } catch {
    failure.value = 'Não foi possível carregar o rascunho deste site.'
  }
}

// O id do site vem da sessão confirmada, não da URL: o `pageId` do endereço é
// só o que o botão "Pré-visualizar" do editor carrega consigo.
watch([site, pageSlug], ([value]) => {
  if (value) load(value.id)
}, { immediate: true })

useHead({ title: 'Pré-visualização do cardápio' })
</script>

<template>
  <EditorAuthGate :site-slug="siteSlug">
    <div>
      <div
        style="
          position: sticky;
          top: 0;
          z-index: 50;
          padding: 10px 16px;
          background: #1f2933;
          color: #fff;
          font-size: 13px;
        "
      >
        Pré-visualização do rascunho — ainda não publicado.
        <a :href="`/${siteSlug}/editor/`" style="color: #ffd166; margin-left: 12px">Voltar ao editor</a>
      </div>

      <p v-if="failure" class="sf-empty" style="margin: 48px auto; max-width: 520px">{{ failure }}</p>

      <StorefrontRenderer v-else-if="storefront" :storefront="storefront" />

      <p v-else class="sf-empty" style="margin: 48px auto; max-width: 520px">Carregando...</p>
    </div>
  </EditorAuthGate>
</template>
