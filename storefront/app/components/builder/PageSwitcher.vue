<script setup lang="ts">
/**
 * Seletor de páginas da topbar do editor.
 *
 * Sem ele o editor só sabia abrir a página que veio na URL: para mexer na
 * página de contato, o cliente teria de descobrir um UUID em algum lugar. Com
 * ele, todo o site é alcançável de dentro do editor — trocar, criar e apagar.
 *
 * Criar e apagar são operações de API comum (`MenuPageViewSet` é um
 * ModelViewSet escopado por tenant), então não há nada de novo no servidor: o
 * que faltava era a tela.
 */
import { createPage, deletePage, fetchSitePages, type BuilderPage } from '~~/services/api/builder-pages'

const props = defineProps<{
  siteId: string
  pageId: string
  /** Sobe quando o título da página aberta muda, para a lista não mentir. */
  refreshKey?: number
}>()

const emit = defineEmits<{ (event: 'open', page: BuilderPage): void }>()

const { slug: siteSlug } = useStorefrontTenant()

const pages = ref<BuilderPage[]>([])
const open = ref(false)
const creating = ref(false)
const busy = ref(false)
const failure = ref('')
const newTitle = ref('')

const current = computed(() => pages.value.find((page) => page.id === props.pageId) ?? null)

async function load() {
  try {
    pages.value = await fetchSitePages(props.siteId)
    failure.value = ''
  } catch {
    failure.value = 'Não foi possível listar as páginas.'
  }
}

/** "Ofertas da semana" → "ofertas-da-semana". */
function slugify(value: string): string {
  return value
    // `NFD` separa a letra do acento e `\p{Diacritic}` remove só o acento:
    // "Promoção" vira "promocao", e não "promoo". Fica em escape nomeado de
    // propósito — uma faixa de caracteres combinantes escrita à mão vira uma
    // regex silenciosamente errada ao passar por um editor que não os preserva.
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
}

async function submitNew() {
  const title = newTitle.value.trim()
  const slug = slugify(title)
  if (!title || !slug || busy.value) return

  busy.value = true
  failure.value = ''
  try {
    const page = await createPage(props.siteId, { title, slug })
    pages.value = await fetchSitePages(props.siteId)
    newTitle.value = ''
    creating.value = false
    open.value = false
    // Abre a página nova direto: criar e continuar na antiga faria o cliente
    // achar que o botão não funcionou.
    emit('open', page)
  } catch (error) {
    const detail = (error as { data?: { error?: { message?: Record<string, string[]> } } })?.data?.error?.message
    const first = detail && Object.values(detail)[0]
    failure.value = (Array.isArray(first) ? first[0] : null) || 'Não foi possível criar a página.'
  } finally {
    busy.value = false
  }
}

async function remove(page: BuilderPage) {
  // A home não pode ser apagada: o site ficaria sem página inicial e o
  // endereço raiz devolveria 404 para o visitante.
  if (page.is_home || busy.value) return
  if (!confirm(`Apagar a página "${page.title}"? O endereço /${siteSlug.value}/${page.slug} sai do ar.`)) return

  busy.value = true
  failure.value = ''
  try {
    await deletePage(page.id)
    pages.value = await fetchSitePages(props.siteId)
    if (page.id === props.pageId) {
      const home = pages.value.find((item) => item.is_home) ?? pages.value[0]
      if (home) emit('open', home)
    }
  } catch {
    failure.value = 'Não foi possível apagar a página.'
  } finally {
    busy.value = false
  }
}

watch(() => [props.siteId, props.refreshKey], () => { if (props.siteId) load() }, { immediate: true })
</script>

<template>
  <div class="sf-pages">
    <button type="button" class="sf-pages__current" @click="open = !open">
      <span>{{ current?.title || 'Páginas' }}</span>
      <small v-if="current">/{{ current.is_home ? '' : current.slug }}</small>
      <MaterialIcon name="expand_more" :size="14" class="sf-pages__chevron" />
    </button>

    <div v-if="open" class="sf-pages__menu">
      <p v-if="failure" class="sf-pages__error">{{ failure }}</p>

      <ul class="sf-pages__list">
        <li v-for="page in pages" :key="page.id" :class="{ 'is-current': page.id === pageId }">
          <button type="button" class="sf-pages__item" @click="emit('open', page); open = false">
            <span>{{ page.title }}</span>
            <small>{{ page.is_home ? 'inicial' : `/${page.slug}` }}</small>
          </button>
          <button
            v-if="!page.is_home"
            type="button"
            class="sf-pages__remove"
            :disabled="busy"
            title="Apagar página"
            @click="remove(page)"
          >
            <MaterialIcon name="close" :size="14" />
          </button>
        </li>
      </ul>

      <form v-if="creating" class="sf-pages__new" @submit.prevent="submitNew">
        <input v-model="newTitle" type="text" placeholder="Nome da página" autofocus>
        <small v-if="newTitle.trim()">Endereço: /{{ siteSlug }}/{{ slugify(newTitle) }}</small>
        <div class="sf-pages__new-actions">
          <button type="button" @click="creating = false">Cancelar</button>
          <button type="submit" class="is-primary" :disabled="busy || !newTitle.trim()">Criar</button>
        </div>
      </form>

      <button v-else type="button" class="sf-pages__add" @click="creating = true">+ Nova página</button>
    </div>
  </div>
</template>
