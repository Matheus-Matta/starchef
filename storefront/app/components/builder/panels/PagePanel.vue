<script setup lang="ts">
/**
 * Configurações da PÁGINA aberta no editor.
 *
 * Título, endereço, página inicial, ordem no menu e SEO — os mesmos campos que
 * o painel administrativo oferece, aqui ao lado do conteúdo que eles nomeiam.
 *
 * Não mexe em `draft_data`: o conteúdo é o canvas, e quem o salva é a topbar.
 * Misturar as duas coisas faria este formulário sobrescrever, com o rascunho
 * que carregou ao abrir, o que o cliente acabou de arrastar no canvas.
 */
import { fetchPage, updatePage, type BuilderPage } from '~~/services/api/builder-pages'

const props = defineProps<{ pageId: string }>()
const emit = defineEmits<{ (event: 'saved', page: BuilderPage): void }>()

const page = ref<BuilderPage | null>(null)
const loading = ref(true)
const saving = ref(false)
const failure = ref('')
const savedAt = ref<Date | null>(null)

const draft = reactive({
  title: '',
  slug: '',
  is_home: false,
  display_order: 0,
  seo: { title: '', description: '', og_image: '', index: true } as Record<string, unknown>,
})

async function load() {
  loading.value = true
  failure.value = ''
  try {
    const loaded = await fetchPage(props.pageId)
    page.value = loaded
    draft.title = loaded.title
    draft.slug = loaded.slug
    draft.is_home = loaded.is_home
    draft.display_order = (loaded as unknown as { display_order?: number }).display_order ?? 0
    draft.seo = { title: '', description: '', og_image: '', index: true, ...(loaded.seo || {}) }
  } catch {
    failure.value = 'Não foi possível carregar as configurações da página.'
  } finally {
    loading.value = false
  }
}

async function save() {
  if (saving.value) return
  saving.value = true
  failure.value = ''
  try {
    const updated = await updatePage(props.pageId, {
      title: draft.title,
      slug: draft.slug,
      is_home: draft.is_home,
      display_order: Number(draft.display_order) || 0,
      seo: draft.seo,
    })
    page.value = updated
    savedAt.value = new Date()
    emit('saved', updated)
  } catch (error) {
    // A API recusa slug repetido e segunda página inicial com mensagem por
    // campo; mostrá-la é mais útil do que um "erro ao salvar" genérico.
    const detail = (error as { data?: { error?: { message?: Record<string, string[]> } } })?.data?.error?.message
    const firstField = detail && Object.values(detail)[0]
    failure.value = (Array.isArray(firstField) ? firstField[0] : null) || 'Não foi possível salvar a página.'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="sf-panel">
    <p v-if="loading" class="sf-panel__hint">Carregando…</p>
    <p v-else-if="failure" class="sf-panel__error">{{ failure }}</p>

    <template v-else>
      <section class="sf-panel__section">
        <h3>Página</h3>
        <label class="sf-field">
          <span>Título</span>
          <input v-model="draft.title" type="text">
        </label>
        <label class="sf-field">
          <span>Endereço (slug)</span>
          <input v-model="draft.slug" type="text" placeholder="promocoes">
        </label>
        <label class="sf-field sf-field--inline">
          <input v-model="draft.is_home" type="checkbox">
          <span>É a página inicial</span>
        </label>
        <label class="sf-field">
          <span>Ordem no menu</span>
          <input v-model="draft.display_order" type="number" min="0">
        </label>
        <p v-if="page" class="sf-panel__hint">
          Situação: {{ page.status === 'published' ? 'publicada' : 'rascunho' }}
          <template v-if="page.has_unpublished_changes"> · há alterações não publicadas</template>
        </p>
      </section>

      <section class="sf-panel__section">
        <h3>SEO da página</h3>
        <label class="sf-field">
          <span>Título no Google</span>
          <input v-model="draft.seo.title" type="text">
        </label>
        <label class="sf-field">
          <span>Descrição no Google</span>
          <textarea v-model="draft.seo.description" rows="3" />
        </label>
        <label class="sf-field">
          <span>Imagem ao compartilhar (URL)</span>
          <input v-model="draft.seo.og_image" type="text">
        </label>
        <label class="sf-field sf-field--inline">
          <input v-model="draft.seo.index" type="checkbox">
          <span>Aparecer em buscadores</span>
        </label>
      </section>

      <div class="sf-panel__foot">
        <span v-if="savedAt" class="sf-panel__hint">Salvo às {{ savedAt.toLocaleTimeString('pt-BR') }}</span>
        <button type="button" class="is-primary" :disabled="saving" @click="save">
          {{ saving ? 'Salvando…' : 'Salvar página' }}
        </button>
      </div>
    </template>
  </div>
</template>
