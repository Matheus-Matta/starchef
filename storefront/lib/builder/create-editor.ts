/**
 * Ponto único de inicialização do GrapesJS.
 *
 * `grapesjs.init()` aparece aqui e em nenhum outro lugar. Espalhar a
 * inicialização faria cada tela do editor configurar um pouco diferente — e a
 * configuração é onde estão as decisões que importam: quais dispositivos
 * existem, quais propriedades de CSS o cliente pode mexer, para onde o upload
 * de imagem vai.
 *
 * O import do GrapesJS é dinâmico e só acontece aqui dentro. É o que mantém o
 * editor fora do bundle do cardápio público — quem abre o site no celular não
 * baixa um editor visual para ver o preço de uma pizza.
 */
import type { Component, Editor, UploadFileFn } from 'grapesjs'
import { registerBlocks, type SectionPreset } from './blocks/register-blocks'
import { canvasStylesheet } from './canvas-styles'
import { PREVIEW_TYPES, registerComponents, type MenuTraitOption } from './components/register-components'
import type { StorefrontPayload } from '~~/types/storefront'
import { DEVICES } from './devices/devices'

export interface CreateEditorOptions {
  container: HTMLElement
  /** Onde os painéis Vue montam a UI do GrapesJS (blocos, camadas, estilo). */
  mounts?: {
    blocks?: string
    layers?: string
    styles?: string
    traits?: string
    selectors?: string
  }
  projectData?: Record<string, unknown>
  /** Endpoint de upload de imagem (a API de assets do Django). */
  assetsUrl?: string
  /** Tema do restaurante, para o canvas parecer com o site de verdade. */
  themeVariables?: Record<string, string>
  /** Seções prontas do backend, oferecidas no painel de blocos. */
  sections?: SectionPreset[]
  /** Menus da conta — vira o seletor "Menu" nos blocos de vitrine e categorias. */
  menuOptions?: MenuTraitOption[]
  /**
   * O payload público do site em edição — produtos, categorias, menus, horários.
   *
   * É o MESMO JSON que o Nuxt usa para renderizar o site, e é o que faz o
   * canvas mostrar o conteúdo de verdade. Sem ele o editor desenhava exemplos,
   * e o cliente montava a página sobre um conteúdo que não existia — inclusive
   * com estrutura diferente da publicada.
   *
   * É um getter porque o conteúdo muda com o editor ABERTO: o painel de Menus
   * troca a foto de um banner e o canvas precisa ler o valor novo. Depois de
   * atualizar a fonte, chame `repaintDataBlocks` para os blocos redesenharem.
   */
  storefront?: () => StorefrontPayload
  /**
   * HTML do cabeçalho do site, desenhado no topo do canvas como referência.
   *
   * O cabeçalho é do SITE e não da página (`MenuSite.header`), então não é um
   * bloco que se possa arrastar. Mas montar a home sem vê-lo é montar às
   * cegas: o cliente não enxerga onde a capa começa em relação ao topo real da
   * página. Entra como decoração fixa, não selecionável.
   */
  headerPreview?: string
  /** Clique no cabeçalho do canvas — abre o painel dele. */
  onHeaderSelect?: () => void
  onChange?: () => void
}

/** Setores do painel de estilo — a lista fechada do que o cliente pode mexer. */
const STYLE_SECTORS = [
  {
    name: 'Layout',
    open: true,
    properties: ['display', 'flex-direction', 'justify-content', 'align-items', 'flex-wrap', 'gap'],
  },
  {
    name: 'Tamanho',
    open: false,
    properties: ['width', 'min-width', 'max-width', 'height', 'min-height', 'max-height'],
  },
  { name: 'Espaçamento', open: false, properties: ['margin', 'padding'] },
  {
    name: 'Tipografia',
    open: false,
    properties: ['font-family', 'font-size', 'font-weight', 'line-height', 'letter-spacing', 'text-align', 'color'],
  },
  {
    name: 'Fundo',
    open: false,
    properties: ['background-color', 'background-image', 'background-size', 'background-position'],
  },
  {
    name: 'Borda',
    open: false,
    properties: ['border-width', 'border-style', 'border-color', 'border-radius'],
  },
  { name: 'Efeitos', open: false, properties: ['box-shadow', 'opacity'] },
]

// Id fixo da folha de estilo do canvas: é por ela que o tema é REESCRITO
// enquanto o cliente mexe nas cores. Criar uma nova a cada alteração deixaria
// dezenas de <style> empilhadas, com a última nem sempre vencendo.
const CANVAS_STYLE_ID = 'sf-canvas-theme'

/**
 * Aplica (ou reaplica) o tema dentro do iframe do canvas.
 *
 * É o que faz o editor mostrar a cor de verdade do restaurante enquanto ele
 * escolhe — sem salvar, sem recarregar. O canvas é um documento isolado, então
 * nada do CSS do Nuxt chega nele sozinho.
 */
export function applyCanvasTheme(editor: Editor, themeVariables: Record<string, string>): void {
  const canvasDocument = editor.Canvas.getDocument()
  if (!canvasDocument) return

  // O `<body>` do canvas veste a classe raiz do site.
  //
  // `blocks.css` tem regras escopadas em `.sf-root` — tipografia dos títulos e,
  // a que mordeu, `img { max-width: 100% }`. No site elas pegam porque o
  // renderer envolve tudo num `<div class="sf-root">`; no canvas não havia
  // equivalente, e a foto de um banner de 1200px estourava a capa e cobria o
  // texto. Vestir a classe no `<body>` faz TODA regra escopada valer aqui
  // dentro, em vez de repetir uma a uma e esquecer da próxima.
  canvasDocument.body?.classList.add('sf-root')

  let style = canvasDocument.getElementById(CANVAS_STYLE_ID) as HTMLStyleElement | null
  if (!style) {
    style = canvasDocument.createElement('style')
    style.id = CANVAS_STYLE_ID
    canvasDocument.head.appendChild(style)
  }
  style.textContent = canvasStylesheet(themeVariables)
}

// O cabeçalho de referência é um elemento solto no `<body>` do canvas, fora da
// árvore de componentes do GrapesJS. Fica com id próprio para ser substituído
// (e não empilhado) quando o cliente muda a configuração do cabeçalho.
const CANVAS_HEADER_ID = 'sf-canvas-header'

export function applyCanvasHeader(editor: Editor, html: string, onSelect?: () => void): void {
  const canvasDocument = editor.Canvas.getDocument()
  const body = canvasDocument?.body
  if (!body) return

  const existing = canvasDocument.getElementById(CANVAS_HEADER_ID)
  if (!html) {
    existing?.remove()
    return
  }

  const holder = (existing as HTMLElement | null) ?? canvasDocument.createElement('div')
  holder.id = CANVAS_HEADER_ID
  holder.className = 'sf-canvas-header'
  holder.innerHTML = html

  // Clicar no cabeçalho abre o painel dele. É como se espera editar algo que
  // está na tela — procurá-lo no fim de um formulário de configurações do site
  // era o motivo de ele parecer não existir. Continua fora da árvore de
  // componentes: selecionável para EDITAR, nunca para arrastar ou apagar.
  if (onSelect) {
    holder.onclick = (event) => {
      event.preventDefault()
      event.stopPropagation()
      onSelect()
    }
  }

  // Sempre o PRIMEIRO filho: o cabeçalho fica acima de tudo na página real, e
  // desenhá-lo no meio do canvas confundiria mais do que ajudaria.
  if (holder.parentElement !== body || body.firstChild !== holder) {
    body.insertBefore(holder, body.firstChild)
  }
}

/**
 * Envia as imagens escolhidas no Asset Manager para a API do Django.
 *
 * Uma requisição por arquivo, com o cookie da sessão do editor e o header de
 * escopo — sem eles o backend responde 401, que era o que acontecia com o
 * upload embutido do GrapesJS. A resposta do Django é o registro do
 * `MenuAsset`; o que interessa aqui é o `url`, e é ele que entra na biblioteca.
 *
 * Um arquivo que falha não derruba os outros: quem manda cinco fotos e erra em
 * uma prefere ficar com quatro a perder todas.
 */
function uploadHandler(editorRef: { current: Editor | null }, assetsUrl?: string): UploadFileFn | undefined {
  if (!assetsUrl) return undefined

  return async function uploadFile(event: DragEvent): Promise<void> {
    // O Asset Manager chama isto tanto no arrastar-e-soltar quanto no clique
    // no seletor de arquivo; os arquivos vêm em lugares diferentes.
    const target = (event as DragEvent & { target?: HTMLInputElement }).target
    const files = event.dataTransfer?.files ?? target?.files
    if (!files?.length) return

    const uploaded: string[] = []

    for (const file of Array.from(files)) {
      const body = new FormData()
      body.append('file', file)
      try {
        const response = await fetch(assetsUrl, {
          method: 'POST',
          body,
          credentials: 'include',
          headers: { 'X-Auth-Scope': 'storefront' },
        })
        if (!response.ok) continue
        const asset = (await response.json()) as { url?: string }
        if (asset?.url) uploaded.push(asset.url)
      } catch {
        // Rede fora ou arquivo recusado: segue para o próximo.
      }
    }

    if (uploaded.length) editorRef.current?.AssetManager.add(uploaded)
  }
}

/**
 * Manda os blocos de dados se redesenharem com o payload atual.
 *
 * Usado depois de mexer no cadastro por fora da página — trocar a foto de um
 * banner no painel de Menus, por exemplo. Recriar o editor também mostraria o
 * conteúdo novo, mas jogaria fora a seleção, o histórico de desfazer e a
 * posição da rolagem; aqui só as prévias voltam a desenhar.
 *
 * O percurso é explícito, e não um evento do GrapesJS, por um motivo que custou
 * uma sessão de depuração: `listenTo(editor, ...)` do Backbone grava o handler
 * no objeto FACHADA, enquanto `editor.trigger(...)` repassa para o modelo
 * interno — o evento saía de um lugar e ninguém escutava no outro, sem erro
 * nenhum na tela.
 *
 * Só os tipos com prévia são tocados (`PREVIEW_TYPES`). Redesenhar um título
 * ou um texto do cliente enquanto ele digita seria pior que não redesenhar
 * nada.
 */
export function repaintDataBlocks(editor: Editor): void {
  const visit = (component: Component) => {
    if (PREVIEW_TYPES.has(String(component.get('type')))) {
      const view = component.view as { render?: () => void } | undefined
      view?.render?.()
    }
    component.components().each(visit)
  }
  editor.getWrapper()?.components().each(visit)
}

export async function createStorefrontEditor(options: CreateEditorOptions): Promise<Editor> {
  const { default: grapesjs } = await import('grapesjs')
  await import('grapesjs/dist/css/grapes.min.css')

  const mounts = options.mounts ?? {}
  // O `uploadFile` é montado ANTES de o editor existir, mas só roda depois —
  // a caixinha quebra esse ovo-e-galinha sem precisar de `let` mutável solto.
  const editorRef: { current: Editor | null } = { current: null }

  const editor = grapesjs.init({
    container: options.container,
    height: '100%',
    width: 'auto',

    // A persistência é nossa, pela API do Django. O storage do GrapesJS
    // gravaria no localStorage do navegador — o cliente perderia a página ao
    // trocar de máquina, e dois editores abertos escreveriam por cima um do
    // outro sem ninguém perceber.
    storageManager: false,

    // Sem os painéis padrão: a UI é Vue. O GrapesJS fica como motor (canvas,
    // drag-and-drop, seleção, undo/redo, árvore de componentes).
    panels: { defaults: [] },

    deviceManager: { devices: DEVICES.map(({ id, name, width, widthMedia }) => ({ id, name, width, widthMedia })) },

    blockManager: mounts.blocks ? { appendTo: mounts.blocks } : undefined,
    layerManager: mounts.layers ? { appendTo: mounts.layers } : undefined,
    traitManager: mounts.traits ? { appendTo: mounts.traits } : undefined,
    selectorManager: mounts.selectors ? { appendTo: mounts.selectors } : undefined,
    styleManager: {
      appendTo: mounts.styles,
      sectors: STYLE_SECTORS,
    },

    // O upload é NOSSO (`uploadFile` abaixo), não o do GrapesJS. Duas razões,
    // e as duas quebravam na prática:
    //  - a requisição precisa do cookie de sessão do editor e do header
    //    `X-Auth-Scope`, que o upload embutido não manda — toda imagem
    //    respondia 401;
    //  - o backend devolve o registro do `MenuAsset` (`{id, url, ...}`), e o
    //    Asset Manager espera `{data: [...]}` — a imagem subia e não aparecia.
    assetManager: { upload: false, autoAdd: true, uploadFile: uploadHandler(editorRef, options.assetsUrl) },

    canvas: {
      styles: [],
    },
  })

  editorRef.current = editor
  editor.Canvas.getConfig().styles = []

  function paintCanvas() {
    applyCanvasTheme(editor, options.themeVariables ?? {})
    applyCanvasHeader(editor, options.headerPreview ?? '', options.onHeaderSelect)
  }

  // `load` cobre a abertura; `canvas:frame:load` cobre a TROCA de frame, que
  // acontece ao mudar de dispositivo. Sem o segundo, escolher "Celular"
  // devolvia um canvas sem tema e sem cabeçalho, e o cliente achava que tinha
  // quebrado alguma coisa.
  editor.on('load', paintCanvas)
  editor.on('canvas:frame:load', paintCanvas)

  registerComponents(editor, options.menuOptions ?? [], options.storefront)
  registerBlocks(editor, options.sections ?? [])

  if (options.projectData && Object.keys(options.projectData).length) {
    editor.loadProjectData(options.projectData)
  }

  if (options.onChange) {
    // Um evento por alteração de pixel seria ruído; quem faz o debounce é o
    // autosave do lado Vue.
    editor.on('component:add component:remove component:update styleable:change', options.onChange)
  }

  return editor
}
