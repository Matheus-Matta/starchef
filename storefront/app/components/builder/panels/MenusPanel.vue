<script setup lang="ts">
/**
 * Painel de MENUS — o conteúdo que os blocos mostram, editável sem sair daqui.
 *
 * Vários blocos não guardam o que exibem: apontam para um menu. O carrossel da
 * capa é um menu de banners, as colunas do rodapé são menus de links, a
 * vitrine curada é um menu de produtos. Antes, trocar a foto de um banner
 * obrigava a fechar o editor, abrir o painel administrativo, achar "Itens de
 * menu" e voltar — para uma alteração cujo resultado só se enxerga no canvas.
 *
 * A separação continua de pé, e é ela que dá sentido ao painel: o menu diz
 * QUAIS itens e em que ordem; o bloco diz COMO eles aparecem. Editar o menu
 * daqui muda o conteúdo em todos os blocos que o usam — inclusive nas outras
 * páginas —, e é por isso que o aviso de alcance fica visível o tempo todo.
 *
 * Menu de origem automática ("mais vendidos", "em promoção") não se edita:
 * seus itens são resposta de consulta, não cadastro. O painel mostra o que ele
 * resolveu hoje, em leitura, em vez de oferecer campos que não gravariam nada.
 *
 * Salvar aqui é IMEDIATO e não passa pelo rascunho da página: menu é cadastro
 * do restaurante, não conteúdo de uma versão. Por isso cada item tem seu botão
 * de salvar, e o canvas se repinta assim que a resposta chega.
 */
import {
  createMenuItem,
  deleteMenuItem,
  fetchMenuItems,
  fetchMenuSummaries,
  updateMenuItem,
  type MenuItemRecord,
  type MenuSummary,
} from '~~/services/api/menus'

const emit = defineEmits<{ (event: 'changed'): void }>()

const menus = ref<MenuSummary[]>([])
const selected = ref('')
const items = ref<MenuItemRecord[]>([])
const loading = ref(true)
const loadingItems = ref(false)
const failure = ref('')

/** Rascunho por item: o que o cliente digitou e ainda não salvou. */
interface Draft {
  title: string
  subtitle: string
  url: string
  display_order: number
  is_active: boolean
  file: File | null
  /** `blob:` da foto escolhida agora — some quando o servidor devolve a dele. */
  filePreview: string
  saving: boolean
  error: string
}

const drafts = reactive<Record<string, Draft>>({})
const openId = ref('')

const TYPE_LABELS: Record<string, string> = {
  product: 'Produto',
  category: 'Categoria',
  image: 'Banner',
  custom: 'Link',
}

const current = computed(() => menus.value.find((menu) => menu.id === selected.value) ?? null)
const isDynamic = computed(() => Boolean(current.value) && current.value?.source !== 'manual')

function draftOf(item: MenuItemRecord): Draft {
  return {
    title: item.title ?? '',
    subtitle: item.subtitle ?? '',
    url: item.url ?? '',
    display_order: item.display_order ?? 0,
    is_active: item.is_active !== false,
    file: null,
    filePreview: '',
    saving: false,
    error: '',
  }
}

async function loadMenus() {
  loading.value = true
  failure.value = ''
  try {
    menus.value = await fetchMenuSummaries()
    if (!selected.value && menus.value.length) selected.value = menus.value[0]!.id
  } catch {
    failure.value = 'Não foi possível carregar os menus. Verifique sua permissão de edição.'
  } finally {
    loading.value = false
  }
}

async function loadItems() {
  if (!selected.value) return
  loadingItems.value = true
  failure.value = ''
  try {
    items.value = await fetchMenuItems(selected.value)
    for (const key of Object.keys(drafts)) delete drafts[key]
    for (const item of items.value) drafts[item.id] = draftOf(item)
  } catch {
    failure.value = 'Não foi possível carregar os itens deste menu.'
    items.value = []
  } finally {
    loadingItems.value = false
  }
}

/** A foto mostrada na linha: a escolhida agora vence a que está salva. */
function thumbOf(item: MenuItemRecord): string {
  return drafts[item.id]?.filePreview || item.image || ''
}

function pickFile(item: MenuItemRecord, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  const draft = drafts[item.id]
  if (!file || !draft) return
  // Prévia local antes do upload: sem ela o cliente escolhe a foto e não vê
  // nada acontecer até salvar, e escolhe de novo achando que falhou.
  if (draft.filePreview) URL.revokeObjectURL(draft.filePreview)
  draft.file = file
  draft.filePreview = URL.createObjectURL(file)
}

async function save(item: MenuItemRecord) {
  const draft = drafts[item.id]
  if (!draft || draft.saving) return
  draft.saving = true
  draft.error = ''
  try {
    const updated = await updateMenuItem(item.id, {
      title: draft.title,
      subtitle: draft.subtitle,
      url: draft.url,
      display_order: draft.display_order,
      is_active: draft.is_active,
      image: draft.file,
    })
    const index = items.value.findIndex((row) => row.id === item.id)
    if (index >= 0) items.value[index] = updated
    if (draft.filePreview) URL.revokeObjectURL(draft.filePreview)
    drafts[item.id] = draftOf(updated)
    // O canvas mostra o menu, não o formulário: sem isto o cliente salvaria a
    // foto nova e continuaria vendo a antiga na página que está montando.
    emit('changed')
  } catch {
    draft.error = 'Não foi possível salvar este item.'
  } finally {
    draft.saving = false
  }
}

const creating = ref(false)

/**
 * Um banner novo, vazio.
 *
 * Criado sem imagem de propósito: o `item_type = image` exige foto na
 * validação do backend, mas exigi-la ANTES de criar significaria um seletor de
 * arquivo solto na tela sem item a que pertencer. Aqui a linha nasce primeiro
 * e a foto entra nela — que é a ordem em que o cliente pensa.
 */
async function addBanner() {
  if (!selected.value || creating.value) return
  creating.value = true
  failure.value = ''
  try {
    const created = await createMenuItem({
      menu: selected.value,
      item_type: 'image',
      title: 'Novo banner',
      display_order: items.value.length,
    })
    items.value = [...items.value, created]
    drafts[created.id] = draftOf(created)
    openId.value = created.id
    emit('changed')
  } catch {
    failure.value = 'Não foi possível criar o banner. Este menu aceita itens manuais?'
  } finally {
    creating.value = false
  }
}

async function remove(item: MenuItemRecord) {
  // eslint-disable-next-line no-alert
  if (!window.confirm(`Remover "${item.label || item.title}" deste menu?`)) return
  try {
    await deleteMenuItem(item.id)
    items.value = items.value.filter((row) => row.id !== item.id)
    delete drafts[item.id]
    emit('changed')
  } catch {
    failure.value = 'Não foi possível remover este item.'
  }
}

watch(selected, loadItems)
onMounted(async () => {
  await loadMenus()
  await loadItems()
})

// Cada `createObjectURL` prende o arquivo na memória até ser liberado.
onBeforeUnmount(() => {
  for (const draft of Object.values(drafts)) {
    if (draft.filePreview) URL.revokeObjectURL(draft.filePreview)
  }
})
</script>

<template>
  <div class="sf-panel">
    <p v-if="loading" class="sf-panel__hint">Carregando…</p>

    <template v-else>
      <p v-if="failure" class="sf-panel__error">{{ failure }}</p>

      <section class="sf-panel__section">
        <h3>Menu</h3>
        <label class="sf-field">
          <span>Qual menu editar</span>
          <select v-model="selected">
            <option v-for="menu in menus" :key="menu.id" :value="menu.id">{{ menu.name }}</option>
          </select>
        </label>
        <p class="sf-panel__hint">
          O menu é o conteúdo; o bloco é a aparência. Mexer aqui muda todos os blocos que apontam
          para <code>{{ current?.slug }}</code> — inclusive em outras páginas.
        </p>
      </section>

      <section class="sf-panel__section">
        <h3>Itens</h3>

        <p v-if="isDynamic" class="sf-panel__hint">
          Este menu é automático ({{ current?.source === 'best_sellers' ? 'mais vendidos'
            : current?.source === 'promotions' ? 'em promoção' : 'consulta do cadastro' }}).
          Os itens abaixo são o que ele resolveu agora e se atualizam sozinhos — não há o que editar.
        </p>

        <p v-if="loadingItems" class="sf-panel__hint">Carregando itens…</p>
        <p v-else-if="!items.length" class="sf-panel__hint">Este menu ainda não tem itens.</p>

        <div v-for="item in items" :key="item.id" class="sf-menuitem">
          <button
            type="button"
            class="sf-menuitem__head"
            :class="{ 'is-open': openId === item.id }"
            @click="openId = openId === item.id ? '' : item.id"
          >
            <span class="sf-menuitem__thumb">
              <img v-if="thumbOf(item)" :src="thumbOf(item)" alt="">
              <MaterialIcon v-else :name="item.item_type === 'image' ? 'image' : 'link'" :size="14" />
            </span>
            <span class="sf-menuitem__label">
              {{ drafts[item.id]?.title || item.label }}
              <small>{{ TYPE_LABELS[item.item_type] ?? item.item_type }}</small>
            </span>
            <MaterialIcon :name="openId === item.id ? 'expand_less' : 'expand_more'" :size="16" />
          </button>

          <div v-if="openId === item.id && !isDynamic" class="sf-menuitem__body">
            <label class="sf-field">
              <span>{{ item.item_type === 'image' ? 'Foto do banner' : 'Foto (substitui a padrão)' }}</span>
              <input type="file" accept="image/jpeg,image/png,image/webp,image/avif,image/gif" @change="pickFile(item, $event)">
            </label>

            <label class="sf-field">
              <span>Título</span>
              <input v-model="drafts[item.id]!.title" type="text" :placeholder="item.label">
            </label>
            <label class="sf-field">
              <span>Subtítulo</span>
              <input v-model="drafts[item.id]!.subtitle" type="text">
            </label>
            <label class="sf-field">
              <span>Link</span>
              <input v-model="drafts[item.id]!.url" type="text" placeholder="/promocoes">
            </label>
            <label class="sf-field">
              <span>Ordem</span>
              <input v-model.number="drafts[item.id]!.display_order" type="number" min="0">
            </label>
            <label class="sf-field sf-field--inline">
              <input v-model="drafts[item.id]!.is_active" type="checkbox">
              <span>Ativo</span>
            </label>

            <p v-if="drafts[item.id]!.error" class="sf-panel__error">{{ drafts[item.id]!.error }}</p>

            <div class="sf-menuitem__actions">
              <button type="button" class="sf-menuitem__remove" @click="remove(item)">Remover</button>
              <button type="button" class="is-primary" :disabled="drafts[item.id]!.saving" @click="save(item)">
                {{ drafts[item.id]!.saving ? 'Salvando…' : 'Salvar item' }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <div v-if="!isDynamic" class="sf-panel__foot">
        <span class="sf-panel__hint">Salva direto no cadastro, sem publicar a página.</span>
        <button type="button" :disabled="creating" @click="addBanner">
          {{ creating ? 'Criando…' : 'Novo banner' }}
        </button>
      </div>
    </template>
  </div>
</template>
