<script setup lang="ts">
/**
 * Painel do CABEÇALHO — antes escondido no meio das configurações do site.
 *
 * O cabeçalho tem quatro grupos de opções (faixa, endereço, busca+ações,
 * navegação) e é a peça que o cliente mais quer mexer depois do tema. Estava
 * no fim de um formulário longo junto com tema, SEO e catálogo, e por isso
 * parecia não existir.
 *
 * Aqui ele tem aba própria, e é alcançável do jeito que se espera: clicando no
 * cabeçalho dentro do canvas. Continua sendo do SITE — não é um bloco, não se
 * apaga — mas passa a ser tão editável quanto qualquer bloco.
 *
 * O canvas acompanha cada tecla: o `watch` profundo emite a cada alteração e o
 * editor redesenha o cabeçalho sem salvar.
 */
import { fetchMenus, fetchSite, updateSite, type MenuOption } from '~~/services/api/builder-pages'
import type { StorefrontHeaderConfig } from '~~/types/storefront'

const props = defineProps<{ siteId: string }>()
const emit = defineEmits<{ (event: 'header', value: StorefrontHeaderConfig): void }>()

/** O cabeçalho com os quatro grupos garantidos, para o `v-model` ter onde escrever. */
type HeaderDraft = StorefrontHeaderConfig & {
  announcement: NonNullable<StorefrontHeaderConfig['announcement']>
  location: NonNullable<StorefrontHeaderConfig['location']>
  search: NonNullable<StorefrontHeaderConfig['search']>
  actions: NonNullable<StorefrontHeaderConfig['actions']>
}

function normalize(header: StorefrontHeaderConfig | undefined): HeaderDraft {
  return {
    sticky: true,
    brand_name: '',
    logo_url: '',
    nav_menu: '',
    secondary_menu: '',
    ...(header || {}),
    announcement: { enabled: true, text: '', highlight: '', secondary: '', url: '', ...(header?.announcement || {}) },
    location: { enabled: true, label: 'Entregar em', value: '', ...(header?.location || {}) },
    search: { enabled: true, placeholder: '', ...(header?.search || {}) },
    actions: { cart: true, profile: true, display: 'icon', cart_label: 'Carrinho', profile_label: 'Entrar', ...(header?.actions || {}) },
  }
}

const draft = ref<HeaderDraft>(normalize(undefined))
const menus = ref<MenuOption[]>([])
const loading = ref(true)
const saving = ref(false)
const failure = ref('')
const savedAt = ref<Date | null>(null)

async function load() {
  loading.value = true
  failure.value = ''
  try {
    const [site, menuList] = await Promise.all([
      fetchSite(props.siteId),
      // Os menus alimentam os dois seletores de navegação; se a listagem
      // falhar por permissão, o resto do painel continua utilizável.
      fetchMenus().catch(() => []),
    ])
    draft.value = normalize(site.header)
    menus.value = menuList
    emit('header', draft.value)
  } catch {
    failure.value = 'Não foi possível carregar o cabeçalho.'
  } finally {
    loading.value = false
  }
}

async function save() {
  if (saving.value) return
  saving.value = true
  failure.value = ''
  try {
    // PATCH só do cabeçalho: mandar o tema junto sobrescreveria o que o painel
    // de Site tivesse acabado de mudar na outra aba.
    const updated = await updateSite(props.siteId, { header: draft.value })
    draft.value = normalize(updated.header)
    emit('header', draft.value)
    savedAt.value = new Date()
  } catch {
    failure.value = 'Não foi possível salvar. Verifique sua permissão de edição do site.'
  } finally {
    saving.value = false
  }
}

// Repinta o canvas enquanto digita, sem salvar. `deep` porque os campos moram
// nos objetos aninhados (faixa, endereço, busca, ações).
watch(draft, (value) => emit('header', value), { deep: true })

onMounted(load)
</script>

<template>
  <div class="sf-panel">
    <p v-if="loading" class="sf-panel__hint">Carregando…</p>

    <template v-else>
      <p v-if="failure" class="sf-panel__error">{{ failure }}</p>

      <section class="sf-panel__section">
        <h3>Marca</h3>
        <p class="sf-panel__hint">
          O cabeçalho aparece em todas as páginas. Não é um bloco: não pode ser apagado no canvas.
        </p>
        <label class="sf-field">
          <span>Nome exibido</span>
          <input v-model="draft.brand_name" type="text">
        </label>
        <label class="sf-field">
          <span>Logo (URL)</span>
          <input v-model="draft.logo_url" type="text">
        </label>
        <label class="sf-field sf-field--inline">
          <input v-model="draft.sticky" type="checkbox">
          <span>Fixo ao rolar a página</span>
        </label>
      </section>

      <section class="sf-panel__section">
        <h3>Faixa de aviso</h3>
        <label class="sf-field sf-field--inline">
          <input v-model="draft.announcement.enabled" type="checkbox">
          <span>Mostrar faixa</span>
        </label>
        <label class="sf-field">
          <span>Trecho em destaque</span>
          <input v-model="draft.announcement.highlight" type="text" placeholder="Frete grátis">
        </label>
        <label class="sf-field">
          <span>Mensagem</span>
          <input v-model="draft.announcement.text" type="text">
        </label>
        <label class="sf-field">
          <span>Mensagem secundária</span>
          <input v-model="draft.announcement.secondary" type="text">
        </label>
        <label class="sf-field">
          <span>Link da faixa</span>
          <input v-model="draft.announcement.url" type="text">
        </label>
        <p class="sf-panel__hint">As cores da faixa saem da paleta, na aba Site.</p>
      </section>

      <section class="sf-panel__section">
        <h3>Endereço de entrega</h3>
        <label class="sf-field sf-field--inline">
          <input v-model="draft.location.enabled" type="checkbox">
          <span>Mostrar cidade</span>
        </label>
        <label class="sf-field">
          <span>Rótulo</span>
          <input v-model="draft.location.label" type="text" placeholder="Entregar em">
        </label>
        <label class="sf-field">
          <span>Cidade</span>
          <input v-model="draft.location.value" type="text">
        </label>
      </section>

      <section class="sf-panel__section">
        <h3>Busca e ações</h3>
        <label class="sf-field sf-field--inline">
          <input v-model="draft.search.enabled" type="checkbox">
          <span>Mostrar busca</span>
        </label>
        <label class="sf-field">
          <span>Texto da busca</span>
          <input v-model="draft.search.placeholder" type="text">
        </label>
        <label class="sf-field sf-field--inline">
          <input v-model="draft.actions.cart" type="checkbox">
          <span>Botão de carrinho</span>
        </label>
        <label class="sf-field sf-field--inline">
          <input v-model="draft.actions.profile" type="checkbox">
          <span>Botão de conta</span>
        </label>
        <label class="sf-field">
          <span>Como os botões aparecem</span>
          <select v-model="draft.actions.display">
            <option value="icon">Só o ícone</option>
            <option value="icon_text">Ícone + texto</option>
            <option value="text">Só o texto</option>
          </select>
        </label>
        <label class="sf-field">
          <span>Texto do carrinho</span>
          <input v-model="draft.actions.cart_label" type="text" placeholder="Carrinho">
        </label>
        <label class="sf-field">
          <span>Texto da conta</span>
          <input v-model="draft.actions.profile_label" type="text" placeholder="Entrar">
        </label>
      </section>

      <section class="sf-panel__section">
        <h3>Navegação</h3>
        <label class="sf-field">
          <span>Menu principal</span>
          <select v-model="draft.nav_menu">
            <option value="">Sem navegação</option>
            <option v-for="menu in menus" :key="menu.id" :value="menu.slug">{{ menu.name }}</option>
          </select>
        </label>
        <label class="sf-field">
          <span>Menu de apoio (direita)</span>
          <select v-model="draft.secondary_menu">
            <option value="">Sem links de apoio</option>
            <option v-for="menu in menus" :key="menu.id" :value="menu.slug">{{ menu.name }}</option>
          </select>
        </label>
        <p class="sf-panel__hint">
          Os itens vêm do cadastro de Menus. Monte a lista lá e ela aparece aqui.
        </p>
      </section>

      <div class="sf-panel__foot">
        <span v-if="savedAt" class="sf-panel__hint">Salvo às {{ savedAt.toLocaleTimeString('pt-BR') }}</span>
        <button type="button" class="is-primary" :disabled="saving" @click="save">
          {{ saving ? 'Salvando…' : 'Salvar cabeçalho' }}
        </button>
      </div>
    </template>
  </div>
</template>
