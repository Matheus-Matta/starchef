<script setup lang="ts">
/**
 * Configurações do SITE, dentro do editor.
 *
 * Tudo o que o model `MenuSite` guarda é editável aqui — tema, SEO,
 * identidade, catálogo — e não só no painel administrativo. O motivo é o ciclo
 * de trabalho: escolher uma cor num formulário de outro aplicativo e só depois
 * abrir o editor para ver como ficou é lento e às cegas. Aqui a cor muda no
 * canvas enquanto o cliente arrasta o seletor.
 *
 * Duas camadas de estado, de propósito:
 *
 * - `draft` é o que está na tela. Toda mudança de tema emite `theme` para o
 *   editor repintar o canvas na hora, SEM salvar.
 * - o servidor só recebe no "Salvar", e recebe um PATCH parcial — `theme` e
 *   `seo` são fundidos com o que já está salvo, então este formulário não
 *   apaga token que ele não exibe.
 */
import { fetchMenus, fetchSite, fetchThemePresets, updateSite, type BuilderSite, type MenuOption, type ThemePreset } from '~~/services/api/builder-pages'
import type { StorefrontTheme } from '~~/types/storefront'

const props = defineProps<{ siteId: string }>()
const emit = defineEmits<{ (event: 'theme', value: StorefrontTheme): void }>()

const site = ref<BuilderSite | null>(null)
const presets = ref<ThemePreset[]>([])
const menus = ref<MenuOption[]>([])
const defaultPreset = ref('')
const loading = ref(true)
const saving = ref(false)
const failure = ref('')
const savedAt = ref<Date | null>(null)

/** Campos editáveis, separados do registro carregado (o "antes"). */
const draft = reactive({
  name: '',
  slug: '',
  is_active: true,
  theme_preset: '',
  catalog: '' as string,
  theme: {} as StorefrontTheme,
  seo: { title: '', description: '', og_image: '', index: true } as Record<string, unknown>,
})

// Ordem e rótulo dos tokens. É uma lista, e não `Object.keys(theme)`, para o
// painel ter ordem estável e nomes em português mesmo quando o tema salvo
// vier incompleto.
// A paleta em grupos, na ordem em que se pensa nela: primeiro as cores de
// marca, depois as superfícies, o texto e por fim as de papel — as que antes
// viviam fixas no CSS e escapavam do tema.
const COLOR_GROUPS: Array<{ title: string; hint?: string; tokens: Array<[keyof StorefrontTheme, string]> }> = [
  {
    title: 'Marca',
    tokens: [
      ['primaryColor', 'Cor principal'],
      ['accentColor', 'Cor de destaque'],
      ['secondaryColor', 'Cor secundária'],
    ],
  },
  {
    title: 'Superfícies',
    tokens: [
      ['backgroundColor', 'Fundo da página'],
      ['surfaceColor', 'Fundo dos blocos'],
      ['borderColor', 'Cor das bordas'],
    ],
  },
  {
    title: 'Texto',
    hint: 'As duas primeiras são o texto SOBRE as cores de ação — branco sobre o principal, escuro sobre o destaque.',
    tokens: [
      ['textColor', 'Cor do texto'],
      ['mutedTextColor', 'Texto secundário'],
      ['onPrimaryColor', 'Texto sobre a cor principal'],
      ['onAccentColor', 'Texto sobre o destaque'],
    ],
  },
  {
    title: 'Cabeçalho',
    hint: 'O cabeçalho aparece em todas as páginas. O conteúdo dele fica na aba Cabeçalho.',
    tokens: [
      ['headerBackgroundColor', 'Fundo do cabeçalho'],
      ['announcementBackgroundColor', 'Fundo da faixa de aviso'],
      ['announcementTextColor', 'Texto da faixa de aviso'],
    ],
  },
  {
    title: 'Sinalização',
    tokens: [
      ['saleColor', 'Selo de promoção'],
      ['whatsappColor', 'Botão de WhatsApp'],
    ],
  },
]

const TEXT_TOKENS: Array<[keyof StorefrontTheme, string, string]> = [
  ['fontFamily', 'Fonte do texto', 'Inter, system-ui, sans-serif'],
  ['headingFontFamily', 'Fonte dos títulos', 'Inter, system-ui, sans-serif'],
  ['borderRadius', 'Arredondamento', '14px'],
  ['containerWidth', 'Largura do conteúdo', '1240px'],
  ['spacing', 'Espaçamento', '24px'],
]

async function load() {
  loading.value = true
  failure.value = ''
  try {
    const [loadedSite, themeCatalog, menuList] = await Promise.all([
      fetchSite(props.siteId),
      fetchThemePresets(),
      // Os menus são opcionais; se a listagem falhar (permissão de cardápio),
      // o resto do painel continua utilizável.
      fetchMenus().catch(() => []),
    ])
    site.value = loadedSite
    presets.value = themeCatalog.presets
    defaultPreset.value = themeCatalog.default
    menus.value = menuList

    draft.name = loadedSite.name || ''
    draft.slug = loadedSite.slug || ''
    draft.is_active = loadedSite.is_active
    draft.theme_preset = loadedSite.theme_preset || ''
    draft.catalog = loadedSite.catalog || ''
    draft.theme = { ...(loadedSite.theme || {}) }
    draft.seo = { title: '', description: '', og_image: '', index: true, ...(loadedSite.seo || {}) }
  } catch {
    failure.value = 'Não foi possível carregar as configurações do site.'
  } finally {
    loading.value = false
  }
}

/** Troca de preset repinta tudo — os tokens do preset substituem os atuais. */
function applyPreset(key: string) {
  draft.theme_preset = key
  const preset = presets.value.find((item) => item.key === key)
  if (!preset) return
  draft.theme = { ...preset.tokens }
  emit('theme', draft.theme)
}

function setToken(token: keyof StorefrontTheme, value: string) {
  draft.theme = { ...draft.theme, [token]: value }
  // Mexer num token à mão solta o rótulo do preset — o servidor faz a mesma
  // conta ao salvar; aqui é só para a tela não mentir enquanto edita.
  draft.theme_preset = ''
  emit('theme', draft.theme)
}

async function save() {
  if (!site.value || saving.value) return
  saving.value = true
  failure.value = ''
  try {
    const updated = await updateSite(props.siteId, {
      name: draft.name,
      slug: draft.slug,
      is_active: draft.is_active,
      // String vazia significa "sem recorte" — a API espera null para limpar
      // o vínculo, e publicaria o cardápio inteiro.
      catalog: draft.catalog || null,
      theme: draft.theme,
      seo: draft.seo,
      ...(draft.theme_preset ? { theme_preset: draft.theme_preset } : {}),
    } as Partial<BuilderSite>)
    site.value = updated
    // O servidor sanitiza e funde: reabastecemos a tela com o que ele gravou,
    // e não com o que mandamos, para o editor mostrar a verdade.
    draft.theme = { ...(updated.theme || {}) }
    draft.theme_preset = updated.theme_preset || ''
    emit('theme', draft.theme)
    savedAt.value = new Date()
  } catch {
    failure.value = 'Não foi possível salvar. Verifique sua permissão de edição do site.'
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
        <h3>Identidade</h3>
        <label class="sf-field">
          <span>Nome do site</span>
          <input v-model="draft.name" type="text" placeholder="Pizzaria Itália">
        </label>
        <label class="sf-field">
          <span>Endereço (slug)</span>
          <input v-model="draft.slug" type="text" placeholder="pizzaria-italia">
        </label>
        <label class="sf-field sf-field--inline">
          <input v-model="draft.is_active" type="checkbox">
          <span>Site no ar</span>
        </label>
        <p v-if="site?.restaurant_name" class="sf-panel__hint">Restaurante: {{ site.restaurant_name }}</p>
        <p v-if="site?.primary_domain" class="sf-panel__hint">Domínio: {{ site.primary_domain }}</p>
      </section>

      <section class="sf-panel__section">
        <h3>Catálogo publicado</h3>
        <label class="sf-field">
          <span>Recorte de produtos</span>
          <select v-model="draft.catalog">
            <option value="">Todo o cardápio ativo do restaurante</option>
            <option v-for="menu in menus" :key="menu.id" :value="menu.id">{{ menu.name }}</option>
          </select>
        </label>
        <p class="sf-panel__hint">
          Define QUAIS produtos o site mostra. Sem recorte, publica o cardápio inteiro.
        </p>
      </section>

      <section class="sf-panel__section">
        <h3>Tema pronto</h3>
        <div class="sf-presets">
          <button
            v-for="preset in presets"
            :key="preset.key"
            type="button"
            class="sf-preset"
            :class="{ 'is-active': draft.theme_preset === preset.key }"
            :title="preset.description"
            @click="applyPreset(preset.key)"
          >
            <span class="sf-preset__swatches">
              <i :style="{ background: preset.tokens.primaryColor }" />
              <i :style="{ background: preset.tokens.accentColor }" />
              <i :style="{ background: preset.tokens.backgroundColor }" />
            </span>
            {{ preset.name }}
            <small v-if="preset.key === defaultPreset">padrão</small>
          </button>
        </div>
        <p v-if="!draft.theme_preset" class="sf-panel__hint">Tema personalizado (cores ajustadas à mão).</p>
      </section>

      <section v-for="group in COLOR_GROUPS" :key="group.title" class="sf-panel__section">
        <h3>{{ group.title }}</h3>
        <p v-if="group.hint" class="sf-panel__hint">{{ group.hint }}</p>
        <label v-for="[token, label] in group.tokens" :key="token" class="sf-field sf-field--color">
          <span>{{ label }}</span>
          <input
            type="color"
            :value="draft.theme[token] || '#000000'"
            @input="setToken(token, ($event.target as HTMLInputElement).value)"
          >
        </label>
      </section>

      <section class="sf-panel__section">
        <h3>Tipografia e espaçamento</h3>
        <label v-for="[token, label, hint] in TEXT_TOKENS" :key="token" class="sf-field">
          <span>{{ label }}</span>
          <input
            type="text"
            :value="draft.theme[token] || ''"
            :placeholder="hint"
            @change="setToken(token, ($event.target as HTMLInputElement).value)"
          >
        </label>
      </section>

      <section class="sf-panel__section">
        <h3>SEO do site</h3>
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
          {{ saving ? 'Salvando…' : 'Salvar site' }}
        </button>
      </div>
    </template>
  </div>
</template>
