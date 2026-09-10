<script setup lang="ts">
/**
 * Casca do editor visual.
 *
 * `.client.vue` não é detalhe: o GrapesJS precisa de DOM e quebraria no SSR.
 * O sufixo garante que nem o import aparece no bundle do servidor, e o
 * `createStorefrontEditor` só é buscado quando esta tela abre — o cardápio
 * público nunca baixa uma linha do editor.
 *
 * Esta é a versão inicial (Fase 1 do plano): topbar, painéis do GrapesJS
 * montados dentro da nossa moldura, save/autosave/publish. A UI Vue própria
 * dos painéis (blocos, camadas, estilo) entra depois, sobre o mesmo motor.
 */
import type { Editor } from 'grapesjs'
import type { Breakpoint } from '~~/types/builder'
import { applyCanvasHeader, applyCanvasTheme, createStorefrontEditor, repaintDataBlocks } from '~~/lib/builder/create-editor'
import { headerPreviewHtml } from '~~/lib/builder/components/previews'
import { DEVICES } from '~~/lib/builder/devices/devices'
import {
  fetchBuilderSchema,
  fetchMenus,
  fetchPage,
  fetchSite,
  publishPage,
  saveDraft,
  type BuilderPage,
} from '~~/services/api/builder-pages'
import { fetchStorefront } from '~~/services/api/storefront'
import { EMPTY_STOREFRONT } from '~~/lib/storefront/resolve'
import { themeToCssVariables } from '~/composables/useStorefrontTheme'
import type { StorefrontHeaderConfig, StorefrontPayload, StorefrontTheme } from '~~/types/storefront'

const props = defineProps<{
  pageId: string
}>()

const canvas = ref<HTMLElement | null>(null)
// `shallowRef`: o editor é um objeto enorme e cheio de referências circulares.
// Torná-lo reativo em profundidade travaria a aba.
const editor = shallowRef<Editor | null>(null)

const pageTitle = ref('')
const siteId = ref('')
// Sobe a cada renomeação/criação de página para o seletor recarregar a lista.
const pagesVersion = ref(0)
// Configuração do cabeçalho do site, para desenhá-lo no topo do canvas.
const header = ref<StorefrontHeaderConfig | null>(null)
const headerMenus = ref<Record<string, { items?: Array<{ title?: string }> }>>({})
// O payload público do site — produtos, categorias, menus, banners. É o que o
// canvas desenha, e MUDA com o editor aberto: o painel de Menus troca a foto
// de um banner e o canvas tem de acompanhar. Por isso mora num ref, e o editor
// recebe um getter em vez do objeto.
const storefront = ref<StorefrontPayload | null>(null)
// As duas laterais são organizadas como no Studio SDK do GrapesJS: cada uma é
// um conjunto de PAINÉIS nomeados atrás de abas, em vez de tudo empilhado numa
// coluna rolante. Empilhado, o painel de estilo nascia abaixo da dobra e o
// cliente não sabia que existia.
//
//   esquerda  → panelBlocks | panelLayers
//   direita   → panelProperties+panelStyles | panelPageSettings | panelHeader | panelGlobalStyles
const leftTab = ref<'blocks' | 'layers'>('blocks')
const rightTab = ref<'element' | 'page' | 'header' | 'menus' | 'site'>('element')
// Laterais recolhidas: telas estreitas e quem quer ver a página inteira.
const leftOpen = ref(true)
const rightOpen = ref(true)
// Tema em edição: o que o canvas está pintando agora, salvo ou não.
const theme = ref<StorefrontTheme | null>(null)
const device = ref<Breakpoint>('desktop')
const dirty = ref(false)
const saving = ref(false)
const publishing = ref(false)
const lastSavedAt = ref<Date | null>(null)
const failure = ref('')

const { slug: siteSlug } = useStorefrontTenant()

const config = useRuntimeConfig()
const assetsUrl = computed(() => `${String(config.public.apiBase).replace(/\/+$/, '')}/api/v1/storefront/assets/`)

const status = computed(() => {
  if (failure.value) return failure.value
  if (saving.value) return 'Salvando...'
  if (dirty.value) return 'Alterações não salvas'
  if (lastSavedAt.value) return `Salvo às ${lastSavedAt.value.toLocaleTimeString('pt-BR')}`
  return 'Sem alterações'
})

const LEFT_TABS = [
  { id: 'blocks', label: 'Blocos', icon: 'widgets' },
  { id: 'layers', label: 'Camadas', icon: 'layers' },
] as const

const RIGHT_TABS = [
  { id: 'element', label: 'Elemento', icon: 'tune' },
  { id: 'page', label: 'Página', icon: 'description' },
  { id: 'header', label: 'Cabeçalho', icon: 'view_headline' },
  { id: 'menus', label: 'Menus', icon: 'list' },
  { id: 'site', label: 'Site', icon: 'palette' },
] as const

// Quantos blocos a página tinha ao ser carregada. É a referência do freio
// contra o salvamento vazio (ver `wouldWipePage`).
const loadedBlockCount = ref(0)

let autosaveTimer: ReturnType<typeof setTimeout> | null = null

/** Blocos de primeiro nível de um project data do GrapesJS. */
function blockCount(project: Record<string, unknown> | undefined): number {
  const pages = (project?.pages ?? []) as Array<{ frames?: Array<{ component?: { components?: unknown[] } }> }>
  return pages.reduce(
    (total, page) =>
      total + (page.frames ?? []).reduce((sum, frame) => sum + (frame.component?.components?.length ?? 0), 0),
    0,
  )
}

/**
 * Este salvamento apagaria a página inteira?
 *
 * Um canvas vazio quase nunca é uma escolha: é sintoma de que o projeto não
 * chegou a carregar (recarga do dev server no meio da montagem, uma resposta
 * perdida). O autosave dispara três segundos depois e grava o vazio por cima
 * do trabalho do cliente — foi exatamente o que aconteceu aqui, e só se
 * percebeu porque o `published_data` ainda tinha o conteúdo.
 *
 * Apagar TUDO continua possível: basta apagar os blocos um a um e salvar, o
 * que passa por `dirty` com o canvas já vazio antes do carregamento contar.
 * O freio só recusa o caso em que a página TINHA blocos, ninguém os apagou, e
 * mesmo assim o projeto a salvar está vazio.
 */
function wouldWipePage(project: Record<string, unknown>): boolean {
  return loadedBlockCount.value > 0 && blockCount(project) === 0
}

function scheduleAutosave() {
  dirty.value = true
  if (autosaveTimer) clearTimeout(autosaveTimer)
  // Espera o cliente parar de mexer. Salvar a cada alteração faria uma
  // requisição por pixel arrastado.
  autosaveTimer = setTimeout(() => void save(), 3000)
}

async function save() {
  if (!editor.value || saving.value) return

  const project = editor.value.getProjectData() as Record<string, unknown>
  if (wouldWipePage(project)) {
    failure.value = 'O editor não conseguiu carregar esta página. Recarregue antes de editar — nada foi salvo.'
    dirty.value = false
    return
  }

  saving.value = true
  failure.value = ''
  try {
    await saveDraft(props.pageId, project)
    dirty.value = false
    lastSavedAt.value = new Date()
  } catch {
    // Mensagem em vez de exceção: o cliente precisa saber que o trabalho não
    // foi gravado, e continuar com a página aberta para tentar de novo.
    failure.value = 'Erro ao salvar. Suas alterações continuam nesta tela.'
  } finally {
    saving.value = false
  }
}

async function publish() {
  if (!editor.value || publishing.value) return
  const project = editor.value.getProjectData() as Record<string, unknown>
  if (wouldWipePage(project)) {
    failure.value = 'O editor não conseguiu carregar esta página. Recarregue antes de publicar — nada foi enviado.'
    return
  }

  publishing.value = true
  failure.value = ''
  try {
    // Publicar sempre grava o rascunho antes: senão a publicação subiria a
    // versão anterior e o cliente juraria que o botão não funcionou.
    await saveDraft(props.pageId, project)
    await publishPage(props.pageId)
    dirty.value = false
    lastSavedAt.value = new Date()
  } catch {
    failure.value = 'Não foi possível publicar. Verifique sua permissão de publicação.'
  } finally {
    publishing.value = false
  }
}

function headerHtml(): string {
  return headerPreviewHtml(
    (header.value ?? {}) as Record<string, unknown>,
    headerMenus.value,
    pageTitle.value || 'Meu restaurante',
  )
}

/**
 * Abre outra página do mesmo site.
 *
 * Grava o rascunho da atual antes de sair: trocar de página é o momento em que
 * o cliente MAIS espera que nada se perca, e o autosave pode estar no meio dos
 * 3 segundos de espera. Depois troca a URL, e o `watch` sobre `pageId`
 * reconstrói o editor com o conteúdo novo.
 */
async function openPage(page: BuilderPage) {
  if (page.id === props.pageId) return
  if (dirty.value) await save()
  await navigateTo(`/${siteSlug.value}/editor/${page.id}`)
}

/**
 * Recarrega o conteúdo do site e repinta os blocos que o mostram.
 *
 * Chamado quando o painel de Menus grava algo — uma foto de banner nova, um
 * link renomeado. O cadastro mudou por fora da página, então o canvas está
 * mostrando o conteúdo velho até alguém reler.
 *
 * Não recria o editor de propósito: recriar mostraria o conteúdo novo, mas
 * jogaria fora a seleção, o histórico de desfazer e a rolagem de quem estava
 * no meio de uma edição.
 */
async function refreshStorefront() {
  try {
    storefront.value = await fetchStorefront({ slug: siteSlug.value })
    headerMenus.value = storefront.value.menus ?? {}
    if (editor.value) {
      repaintDataBlocks(editor.value)
      // O cabeçalho é desenhado à parte (não é um bloco), então precisa do
      // seu próprio repinte para a navegação nova aparecer.
      applyCanvasHeader(editor.value, headerHtml())
    }
  } catch {
    failure.value = 'Não foi possível recarregar o conteúdo do site.'
  }
}

/** O painel de Site emite a cada alteração: repinta o canvas sem salvar. */
function onThemeChange(next: StorefrontTheme) {
  theme.value = next
  if (editor.value) applyCanvasTheme(editor.value, themeToCssVariables(next))
}

/** O painel de Site também mexe no cabeçalho; o canvas acompanha na hora. */
function onHeaderChange(next: StorefrontHeaderConfig) {
  header.value = next
  if (editor.value) applyCanvasHeader(editor.value, headerHtml())
}

function setDevice(id: Breakpoint) {
  device.value = id
  editor.value?.setDevice(DEVICES.find((item) => item.id === id)?.name ?? 'Desktop')
}

async function mountEditor() {
  if (!canvas.value) return
  failure.value = ''
  try {
    // Página, contrato do builder e menus da conta em paralelo: são
    // independentes entre si, e o editor só abre quando os três chegam. Os
    // menus alimentam o seletor "Menu" dos blocos de vitrine e categorias — se
    // a listagem falhar (permissão de cardápio), o editor abre sem esse
    // seletor em vez de travar.
    const [page, schema, menuList] = await Promise.all([
      fetchPage(props.pageId),
      fetchBuilderSchema(),
      fetchMenus().catch(() => []),
    ])
    pageTitle.value = page.title
    siteId.value = page.site
    loadedBlockCount.value = blockCount(page.draft_data as Record<string, unknown>)

    // O canvas precisa das cores REAIS do restaurante. Sem isto ele pintava
    // sempre com o tema padrão, e o cliente só descobria como a página tinha
    // ficado depois de publicar.
    const site = await fetchSite(page.site)
    theme.value = site.theme ?? null
    header.value = site.header ?? null

    // O payload PÚBLICO — o mesmo que o Nuxt usa para renderizar o site — é o
    // que faz o canvas mostrar o conteúdo de verdade: produtos, categorias,
    // banners e links de rodapé. Sem ele o editor desenhava exemplos, e o
    // cliente montava a página sobre um conteúdo que não existia.
    //
    // Falhar aqui não impede editar: o editor abre com os blocos vazios (o
    // mesmo vazio que o site mostraria), em vez de travar.
    try {
      storefront.value = await fetchStorefront({ slug: siteSlug.value })
      headerMenus.value = storefront.value.menus ?? {}
      if (!header.value) header.value = storefront.value.site?.header ?? null
    } catch {
      headerMenus.value = {}
    }

    editor.value = await createStorefrontEditor({
      container: canvas.value,
      projectData: page.draft_data as Record<string, unknown>,
      assetsUrl: assetsUrl.value,
      themeVariables: themeToCssVariables(theme.value),
      headerPreview: headerHtml(),
      menuOptions: menuList.map((menu) => ({ slug: menu.slug, name: menu.name })),
      storefront: () => storefront.value ?? EMPTY_STOREFRONT,
      // Clicar no cabeçalho dentro do canvas abre o painel dele — o mesmo
      // gesto que se usa para qualquer bloco.
      onHeaderSelect: () => {
        rightTab.value = 'header'
        rightOpen.value = true
      },
      // Seções prontas do backend — as mesmas peças da home padrão.
      sections: schema.sections ?? [],
      mounts: {
        blocks: '#sf-panel-blocks',
        layers: '#sf-panel-layers',
        styles: '#sf-panel-styles',
        traits: '#sf-panel-traits',
        selectors: '#sf-panel-selectors',
      },
      onChange: scheduleAutosave,
    })

    // Selecionar um bloco no canvas leva para a aba de configuração dele.
    // Sem isto, quem tinha acabado de mexer no cabeçalho clicava num bloco e
    // continuava vendo o formulário do cabeçalho.
    editor.value.on('component:selected', () => {
      rightTab.value = 'element'
      rightOpen.value = true
    })
  } catch {
    failure.value = 'Não foi possível abrir o editor. Recarregue a página e tente de novo.'
  }
}

function destroyEditor() {
  if (autosaveTimer) clearTimeout(autosaveTimer)
  autosaveTimer = null
  editor.value?.destroy()
  editor.value = null
  dirty.value = false
}

onMounted(mountEditor)

// Trocar de página no seletor muda a rota, e a rota muda esta prop. O editor é
// recriado do zero: reaproveitar a instância obrigaria a limpar canvas, undo,
// seleção e estilos à mão, e sobra sempre um resíduo da página anterior.
watch(() => props.pageId, async () => {
  destroyEditor()
  await nextTick()
  await mountEditor()
})

onBeforeUnmount(destroyEditor)
</script>

<template>
  <div class="sf-builder">
    <header class="sf-builder__topbar">
      <div class="sf-builder__title">
        <PageSwitcher
          v-if="siteId"
          :site-id="siteId"
          :page-id="pageId"
          :refresh-key="pagesVersion"
          @open="openPage"
        />
        <strong v-else>{{ pageTitle || 'Editor do cardápio' }}</strong>
        <span class="sf-builder__status">{{ status }}</span>
      </div>

      <div class="sf-builder__devices">
        <button
          v-for="item in DEVICES"
          :key="item.id"
          type="button"
          :class="{ 'is-active': device === item.id }"
          @click="setDevice(item.id)"
        >
          {{ item.name }}
        </button>
      </div>

      <div class="sf-builder__actions">
        <button type="button" @click="editor?.UndoManager.undo()">
          <MaterialIcon name="undo" :size="16" />
          Desfazer
        </button>
        <button type="button" @click="editor?.UndoManager.redo()">
          <MaterialIcon name="redo" :size="16" />
          Refazer
        </button>
        <NuxtLink
          v-if="siteId"
          :to="`/${siteSlug}/preview/${pageId}`"
          target="_blank"
          class="sf-builder__link"
        >
          <MaterialIcon name="visibility" :size="16" />
          Pré-visualizar
        </NuxtLink>
        <button type="button" :disabled="saving" @click="save()">
          <MaterialIcon name="save" :size="16" />
          Salvar
        </button>
        <button type="button" class="is-primary" :disabled="publishing" @click="publish()">
          <MaterialIcon name="publish" :size="16" />
          {{ publishing ? 'Publicando...' : 'Publicar' }}
        </button>
      </div>
    </header>

    <div class="sf-builder__body">
      <aside class="sf-builder__sidebar" :class="{ 'is-collapsed': !leftOpen }">
        <div v-if="leftOpen" class="sf-builder__tabs" role="tablist">
          <button
            v-for="tab in LEFT_TABS"
            :key="tab.id"
            type="button"
            role="tab"
            :aria-selected="leftTab === tab.id"
            :class="{ 'is-active': leftTab === tab.id }"
            @click="leftTab = tab.id"
          >
            <MaterialIcon :name="tab.icon" :size="14" />
            {{ tab.label }}
          </button>
        </div>

        <!-- Os painéis do GrapesJS montam em elementos fixos e não podem ser
             destruídos ao trocar de aba: o editor perderia a referência. Por
             isso ficam sempre no DOM, só escondidos. -->
        <div v-show="leftOpen && leftTab === 'blocks'" class="sf-builder__panel">
          <div id="sf-panel-blocks" />
        </div>
        <div v-show="leftOpen && leftTab === 'layers'" class="sf-builder__panel">
          <div id="sf-panel-layers" />
        </div>

        <button
          type="button"
          class="sf-builder__collapse sf-builder__collapse--left"
          :title="leftOpen ? 'Recolher painel' : 'Abrir painel'"
          @click="leftOpen = !leftOpen"
        >
          <MaterialIcon :name="leftOpen ? 'chevron_left' : 'chevron_right'" :size="14" />
        </button>
      </aside>

      <main ref="canvas" class="sf-builder__canvas" />

      <aside class="sf-builder__sidebar sf-builder__sidebar--right" :class="{ 'is-collapsed': !rightOpen }">
        <div v-if="rightOpen" class="sf-builder__tabs" role="tablist">
          <button
            v-for="tab in RIGHT_TABS"
            :key="tab.id"
            type="button"
            role="tab"
            :aria-selected="rightTab === tab.id"
            :class="{ 'is-active': rightTab === tab.id }"
            @click="rightTab = tab.id"
          >
            <MaterialIcon :name="tab.icon" :size="14" />
            {{ tab.label }}
          </button>
        </div>

        <div v-show="rightOpen && rightTab === 'element'" class="sf-builder__panel">
          <h2>Configurações do bloco</h2>
          <div id="sf-panel-traits" />
          <h2>Estilo</h2>
          <div id="sf-panel-selectors" />
          <div id="sf-panel-styles" />
        </div>

        <div v-if="rightOpen && rightTab === 'page'" class="sf-builder__panel">
          <PagePanel :page-id="pageId" @saved="pageTitle = $event.title; pagesVersion++" />
        </div>

        <div v-if="rightOpen && rightTab === 'header' && siteId" class="sf-builder__panel">
          <HeaderPanel :site-id="siteId" @header="onHeaderChange" />
        </div>

        <div v-if="rightOpen && rightTab === 'menus'" class="sf-builder__panel">
          <MenusPanel @changed="refreshStorefront" />
        </div>

        <div v-if="rightOpen && rightTab === 'site' && siteId" class="sf-builder__panel">
          <SitePanel :site-id="siteId" @theme="onThemeChange" />
        </div>

        <button
          type="button"
          class="sf-builder__collapse sf-builder__collapse--right"
          :title="rightOpen ? 'Recolher painel' : 'Abrir painel'"
          @click="rightOpen = !rightOpen"
        >
          <MaterialIcon :name="rightOpen ? 'chevron_right' : 'chevron_left'" :size="14" />
        </button>
      </aside>
    </div>
  </div>
</template>

<style>
@import '~/assets/css/builder.css';
</style>
