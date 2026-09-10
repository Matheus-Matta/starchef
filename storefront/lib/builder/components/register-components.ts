/**
 * Tipos de componente do editor.
 *
 * Cada tipo declara três coisas que valem mais do que a aparência dentro do
 * canvas:
 *
 * - **onde pode ser solto** (`draggable`/`droppable`), o que evita páginas
 *   estruturalmente inválidas — um `sf-product-grid` dentro de um título, por
 *   exemplo;
 * - **quais propriedades de estilo aceita** (`stylable`), para o painel não
 *   oferecer a um bloco de vitrine as 200 propriedades de CSS que existem;
 * - **quais configurações funcionais tem** (`traits`) — categoria, ordenação,
 *   colunas. Trait é configuração, nunca CSS: espaçamento e cor pertencem ao
 *   painel de estilo.
 *
 * O que o canvas desenha é uma REPRESENTAÇÃO. Quem desenha o site de verdade é
 * o renderer Vue; aqui basta o cliente reconhecer o bloco que está movendo.
 */
import type { AddComponentTypeOptions, Component, ComponentDefinition, Editor } from 'grapesjs'
import { COMPONENT_TYPES } from '../registry/components'
import {
  announcementPreview,
  badgePreview,
  categoriesPreview,
  deliveryPreview,
  filterBarPreview,
  footerPreview,
  heroPreview,
  openingHoursPreview,
  paymentMethodsPreview,
  placeholder,
  productGridPreview,
  ratingPreview,
  restaurantInfoPreview,
  searchPreview,
  socialLinksPreview,
  whatsappPreview,
} from './previews'
import { EMPTY_STOREFRONT } from '~~/lib/storefront/resolve'
import type { StorefrontPayload } from '~~/types/storefront'

const BOX_STYLES = [
  'width', 'max-width', 'min-height', 'height',
  'padding', 'margin', 'gap',
  'display', 'flex-direction', 'justify-content', 'align-items', 'flex-wrap',
  'background-color', 'background-image', 'background-size', 'background-position',
  'border', 'border-radius', 'box-shadow', 'opacity',
]

const TEXT_STYLES = [
  'font-family', 'font-size', 'font-weight', 'line-height', 'letter-spacing',
  'text-align', 'text-transform', 'color', 'margin', 'padding',
]

/**
 * Liga os traits de um tipo ao objeto `props` do componente.
 *
 * Sem isto, trait é enfeite: o GrapesJS grava o valor como ATRIBUTO HTML, e o
 * renderer lê `node.props` — o cliente mexeria em "mostrar preço" e nada
 * mudaria no site. O `changeProp` manda o valor para uma propriedade do
 * modelo, e o `init` faz as duas pontas se encontrarem: semeia os traits com o
 * que veio salvo do backend e devolve toda alteração para dentro de `props`.
 *
 * `props` é o contrato com o compiler, e é o mesmo formato que o backend já
 * escreve na home padrão — por isso a ida e a volta usam a mesma chave.
 */
interface TraitSpec {
  type: string
  name: string
  label: string
  options?: Array<{ id: string; name: string }>
  valueTrue?: string | boolean
  valueFalse?: string | boolean
}

type PreviewFn = (props: Record<string, unknown>) => string

/**
 * Os tipos que desenham DADOS — vitrine, capa, categorias, rodapé.
 *
 * O payload que eles leem é buscado uma vez, mas MUDA enquanto o editor está
 * aberto: o painel de Menus grava uma foto de banner nova, e o canvas tem de
 * acompanhar sem recriar o editor (o que perderia a seleção, o histórico de
 * desfazer e a rolagem). `repaintDataBlocks` percorre a árvore e redesenha só
 * estes — um título ou um texto do cliente não tem por que ser tocado.
 *
 * O conjunto é preenchido no registro em vez de escrito à mão: uma lista
 * paralela ficaria desatualizada no dia em que um bloco novo ganhasse prévia.
 * Registrar de novo (outro editor) apenas reinsere os mesmos nomes.
 */
export const PREVIEW_TYPES = new Set<string>()

function propsType(
  type: string,
  defaults: Record<string, unknown> & { traits: TraitSpec[] },
  preview?: PreviewFn,
): AddComponentTypeOptions {
  if (preview) PREVIEW_TYPES.add(type)
  const names = defaults.traits.map((trait) => trait.name).filter(Boolean)
  const traits = defaults.traits.map((trait) => ({ ...trait, changeProp: true }))

  return {
    model: {
      defaults: { ...defaults, traits } as ComponentDefinition,

      init(this: Component) {
        const stored = { ...((this.get('props') as Record<string, unknown>) ?? {}) }
        for (const name of names) {
          if (stored[name] !== undefined) this.set(name, stored[name], { silent: true })
        }

        this.on(names.map((name) => `change:${name}`).join(' '), () => {
          const next = { ...((this.get('props') as Record<string, unknown>) ?? {}) }
          for (const name of names) {
            const value = this.get(name)
            if (value !== undefined) next[name] = value
          }
          this.set('props', next)
        })
      },
    },

    // A prévia é desenhada pela VIEW, e nunca gravada no modelo. Escrevê-la em
    // `content` seria mais simples, mas o `content` é serializado e enviado ao
    // backend: cada bloco de vitrine levaria junto um punhado de cartões de
    // mentira, inflando o JSON da página (que tem teto de bytes) e sujando o
    // conteúdo publicado com HTML que não é do cliente.
    ...(preview
      ? {
          view: {
            init(this: { listenTo: (obj: unknown, ev: string, cb: () => void) => void; model: Component; render: () => void }) {
              // Redesenha quando um trait muda — é o que faz "mostrar preço"
              // apagar o preço no canvas na hora, e não só depois de publicar.
              this.listenTo(this.model, 'change:props', this.render)
            },
            onRender(this: { el: HTMLElement; model: Component }) {
              this.el.innerHTML = preview((this.model.get('props') as Record<string, unknown>) ?? {})
            },
          },
        }
      : {}),
  }
}

export interface MenuTraitOption {
  slug: string
  name: string
}

/**
 * `getData` devolve o payload público do PRÓPRIO site em edição — o mesmo JSON
 * que o Nuxt usa para renderizar a página publicada. É o que permite ao canvas
 * desenhar o catálogo real em vez de exemplos.
 *
 * É um GETTER, e não o payload: o conteúdo muda com o editor aberto (o painel
 * de Menus troca a foto de um banner) e cada prévia precisa ler o valor da vez.
 * Guardar o objeto aqui congelaria o canvas na versão de quando o editor
 * abriu. Continua sem estado mutável de módulo — quem é dono do payload é o
 * componente que criou o editor.
 */
export function registerComponents(
  editor: Editor,
  menuOptions: MenuTraitOption[] = [],
  getData: () => StorefrontPayload = () => EMPTY_STOREFRONT,
): void {
  const { Components } = editor

  // Opção de menu, oferecida no topo dos blocos que mostram uma lista
  // (vitrines e categorias). É a mesma lista de `menu.Menu` que já alimenta a
  // navegação do cabeçalho e do rodapé — o restaurante monta a curadoria uma
  // vez (produtos escolhidos a dedo, em promoção, mais vendidos…) e reaproveita
  // onde quiser, em vez de reconfigurar categoria/ordenação bloco a bloco.
  const MENU_TRAIT_OPTIONS = [
    { id: '', name: 'Nenhum — usar os filtros abaixo' },
    ...menuOptions.map((menu) => ({ id: menu.slug, name: menu.name })),
  ]

  Components.addType(COMPONENT_TYPES.SECTION, {
    model: {
      defaults: {
        tagName: 'section',
        name: 'Seção',
        droppable: true,
        stylable: BOX_STYLES,
        style: { padding: '64px 0' },
      },
    },
  })

  Components.addType(COMPONENT_TYPES.CONTAINER, {
    model: {
      defaults: {
        tagName: 'div',
        name: 'Contêiner',
        droppable: true,
        stylable: BOX_STYLES,
        style: {
          width: '100%',
          'max-width': 'var(--sf-container-width)',
          margin: '0 auto',
          padding: '0 24px',
        },
      },
    },
  })

  for (const [type, name] of [
    [COMPONENT_TYPES.ROW, 'Linha'],
    [COMPONENT_TYPES.COLUMN, 'Coluna'],
    [COMPONENT_TYPES.BANNER, 'Banner'],
  ] as Array<[string, string]>) {
    Components.addType(type, {
      model: { defaults: { tagName: 'div', name, droppable: true, stylable: BOX_STYLES } },
    })
  }

  // A capa é configuração, não contêiner: `droppable: false` de propósito. Um
  // botão arrastado para fora dela deixaria a capa sem chamada para ação, e
  // quem descobre é o cliente, depois de publicar.
  Components.addType(
    COMPONENT_TYPES.HERO,
    propsType(
      COMPONENT_TYPES.HERO,
      {
        tagName: 'section',
        name: 'Capa promocional',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [
          {
            type: 'select',
            name: 'menu',
            label: 'Menu de banners (vazio = uma capa só)',
            options: MENU_TRAIT_OPTIONS,
          },
          { type: 'text', name: 'title', label: 'Título' },
          { type: 'text', name: 'highlight', label: 'Trecho em destaque' },
          { type: 'text', name: 'description', label: 'Descrição' },
          { type: 'text', name: 'cta_label', label: 'Texto do botão' },
          { type: 'text', name: 'cta_url', label: 'Link do botão' },
          { type: 'text', name: 'image', label: 'Imagem (URL)' },
          {
            type: 'select',
            name: 'image_position',
            label: 'Posição da imagem',
            options: [
              { id: 'right-bottom', name: 'Direita, apoiada' },
              { id: 'right-center', name: 'Direita, centralizada' },
              { id: 'left-bottom', name: 'Esquerda, apoiada' },
              { id: 'left-center', name: 'Esquerda, centralizada' },
            ],
          },
          { type: 'text', name: 'image_width', label: 'Largura da imagem' },
          { type: 'text', name: 'background', label: 'Cor de fundo' },
          {
            type: 'select',
            name: 'align',
            label: 'Alinhamento',
            options: [
              { id: 'left', name: 'Esquerda' },
              { id: 'center', name: 'Centro' },
              { id: 'right', name: 'Direita' },
            ],
          },
          { type: 'text', name: 'padding', label: 'Espaçamento interno' },
          { type: 'text', name: 'height', label: 'Altura (desktop)' },
          // Medida por dispositivo: a capa que respira em 1360px sufoca em 375px.
          { type: 'text', name: 'height_tablet', label: 'Altura (tablet)' },
          { type: 'text', name: 'height_mobile', label: 'Altura (celular)' },
          { type: 'text', name: 'padding_mobile', label: 'Espaçamento interno (celular)' },
          {
            type: 'select',
            name: 'align_mobile',
            label: 'Alinhamento (celular)',
            options: [
              { id: 'left', name: 'Esquerda' },
              { id: 'center', name: 'Centro' },
              { id: 'right', name: 'Direita' },
            ],
          },
          { type: 'checkbox', name: 'decorations', label: 'Círculos decorativos', valueTrue: true, valueFalse: false },
        ],
      },
      (props) => heroPreview(props, getData()),
    ),
  )

  Components.addType(COMPONENT_TYPES.HEADING, {
    model: {
      defaults: {
        tagName: 'h2',
        name: 'Título',
        droppable: false,
        editable: true,
        content: 'Título da seção',
        stylable: TEXT_STYLES,
        traits: [
          {
            type: 'select',
            name: 'tagName',
            label: 'Nível',
            options: [
              { id: 'h1', name: 'H1' },
              { id: 'h2', name: 'H2' },
              { id: 'h3', name: 'H3' },
            ],
          },
        ],
      },
    },
  })

  Components.addType(COMPONENT_TYPES.TEXT, {
    model: {
      defaults: {
        tagName: 'p',
        name: 'Texto',
        droppable: false,
        editable: true,
        content: 'Escreva aqui o texto desta seção.',
        stylable: TEXT_STYLES,
      },
    },
  })

  Components.addType(COMPONENT_TYPES.IMAGE, {
    extend: 'image',
    model: {
      defaults: {
        name: 'Imagem',
        droppable: false,
        stylable: [...BOX_STYLES, 'object-fit', 'aspect-ratio'],
      },
    },
  })

  Components.addType(COMPONENT_TYPES.BUTTON, {
    model: {
      defaults: {
        tagName: 'a',
        name: 'Botão',
        droppable: false,
        editable: true,
        content: 'Ver cardápio',
        attributes: { href: '#cardapio' },
        stylable: [...TEXT_STYLES, ...BOX_STYLES],
        traits: [
          { type: 'text', name: 'href', label: 'Link' },
          {
            type: 'select',
            name: 'target',
            label: 'Abrir em',
            options: [
              { id: '', name: 'Mesma aba' },
              { id: '_blank', name: 'Nova aba' },
            ],
          },
        ],
      },
    },
  })

  Components.addType(COMPONENT_TYPES.SPACER, {
    model: {
      defaults: {
        tagName: 'div',
        name: 'Espaço',
        droppable: false,
        stylable: ['height', 'min-height'],
        style: { 'min-height': '48px' },
      },
    },
  })

  Components.addType(COMPONENT_TYPES.DIVIDER, {
    model: {
      defaults: { tagName: 'hr', name: 'Divisória', droppable: false, stylable: ['margin', 'border'] },
    },
  })

  // ── Blocos de dados ───────────────────────────────────────────────────────
  // Não aceitam filhos e não têm conteúdo editável: o que aparece no site é
  // montado pelo renderer com os produtos reais. O canvas mostra um marcador,
  // e o que fica salvo são só as configurações abaixo.
  // ── Vitrines ───────────────────────────────────────────────────────────
  // `sf-product-grid`, `sf-promotions`, `sf-featured-products` e
  // `sf-product-carousel` caem TODOS no mesmo componente do renderer
  // (`SfProductGrid`), então precisam da mesma configuração. Antes só a
  // vitrine tinha traits: o cliente arrastava "Promoções" e não conseguia
  // escolher nem quantas colunas queria.
  const SHOWCASE_TRAITS: TraitSpec[] = [
    {
      type: 'select',
      name: 'menu',
      label: 'Menu (define os itens exibidos)',
      options: MENU_TRAIT_OPTIONS,
    },
    {
      type: 'select',
      name: 'layout',
      label: 'Formato',
      options: [
        { id: 'grid', name: 'Grade' },
        { id: 'carousel', name: 'Carrossel (rola para o lado)' },
      ],
    },
    { type: 'text', name: 'category_id', label: 'Categoria (vazio = todas, ignorado se houver menu)' },
    {
      type: 'select',
      name: 'sort',
      label: 'Ordenação',
      options: [
        { id: 'default', name: 'Padrão' },
        { id: 'name', name: 'Nome' },
        { id: 'price_asc', name: 'Menor preço' },
        { id: 'price_desc', name: 'Maior preço' },
      ],
    },
    { type: 'number', name: 'limit', label: 'Máximo de produtos (0 = todos)' },
    { type: 'number', name: 'columns_desktop', label: 'Colunas no computador' },
    { type: 'number', name: 'columns_tablet', label: 'Colunas no tablet' },
    { type: 'number', name: 'columns_mobile', label: 'Colunas no celular' },
    { type: 'checkbox', name: 'show_image', label: 'Mostrar imagem', valueTrue: true, valueFalse: false },
    { type: 'checkbox', name: 'show_description', label: 'Mostrar descrição', valueTrue: true, valueFalse: false },
    { type: 'checkbox', name: 'show_price', label: 'Mostrar preço', valueTrue: true, valueFalse: false },
    { type: 'checkbox', name: 'show_button', label: 'Mostrar botão', valueTrue: true, valueFalse: false },
    { type: 'checkbox', name: 'show_badges', label: 'Mostrar selos', valueTrue: true, valueFalse: false },
    { type: 'checkbox', name: 'show_old_price', label: 'Mostrar preço antigo', valueTrue: true, valueFalse: false },
    { type: 'checkbox', name: 'show_rating', label: 'Mostrar nota/tempo', valueTrue: true, valueFalse: false },
  ]

  const SHOWCASES: Array<[string, string]> = [
    [COMPONENT_TYPES.PRODUCT_GRID, 'Vitrine de produtos'],
    [COMPONENT_TYPES.PROMOTIONS, 'Ofertas'],
    [COMPONENT_TYPES.FEATURED_PRODUCTS, 'Destaques'],
    [COMPONENT_TYPES.PRODUCT_CAROUSEL, 'Carrossel de produtos'],
  ]

  for (const [type, name] of SHOWCASES) {
    Components.addType(
      type,
      propsType(
        type,
        {
          tagName: 'div',
          name,
          droppable: false,
          editable: false,
          stylable: BOX_STYLES,
          traits: SHOWCASE_TRAITS,
        },
        // `type` distingue vitrine, ofertas e carrossel: é o mesmo valor que
        // o renderer recebe em `node.type`, e é o que faz "Ofertas" mostrar só
        // promoções aqui dentro também.
        (props) => productGridPreview(props, getData(), type),
      ),
    )
  }

  Components.addType(
    COMPONENT_TYPES.CATEGORIES,
    propsType(
      COMPONENT_TYPES.CATEGORIES,
      {
        tagName: 'nav',
        name: 'Categorias',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [
          {
            type: 'select',
            name: 'menu',
            label: 'Menu (define quais categorias aparecem)',
            options: MENU_TRAIT_OPTIONS,
          },
          {
            type: 'select',
            name: 'layout',
            label: 'Formato',
            options: [
              { id: 'chips', name: 'Etiquetas lado a lado' },
              { id: 'list', name: 'Lista' },
            ],
          },
          { type: 'number', name: 'limit', label: 'Máximo de categorias (0 = todas)' },
          {
            type: 'checkbox',
            name: 'show_all',
            label: 'Incluir subcategorias (ignorado se houver menu)',
            valueTrue: true,
            valueFalse: false,
          },
        ],
      },
      (props) => categoriesPreview(props, getData()),
    ),
  )

  Components.addType(
    COMPONENT_TYPES.BADGE,
    propsType(
      COMPONENT_TYPES.BADGE,
      {
        tagName: 'span',
        name: 'Selo',
        droppable: false,
        editable: false,
        stylable: TEXT_STYLES,
        traits: [
          { type: 'text', name: 'text', label: 'Texto' },
          {
            type: 'select',
            name: 'tone',
            label: 'Cor',
            options: [
              { id: 'accent', name: 'Destaque' },
              { id: 'sale', name: 'Promoção' },
              { id: 'info', name: 'Informativo' },
              { id: 'muted', name: 'Neutro' },
            ],
          },
        ],
      },
      badgePreview,
    ),
  )

  Components.addType(
    COMPONENT_TYPES.RATING,
    propsType(
      COMPONENT_TYPES.RATING,
      {
        tagName: 'span',
        name: 'Nota',
        droppable: false,
        editable: false,
        stylable: TEXT_STYLES,
        traits: [
          { type: 'text', name: 'value', label: 'Nota (0 a 5)' },
          { type: 'text', name: 'total', label: 'Escala' },
        ],
      },
      ratingPreview,
    ),
  )

  Components.addType(
    COMPONENT_TYPES.ANNOUNCEMENT_BAR,
    propsType(
      COMPONENT_TYPES.ANNOUNCEMENT_BAR,
      {
        tagName: 'div',
        name: 'Faixa de aviso',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [
          { type: 'text', name: 'message', label: 'Mensagem' },
          { type: 'checkbox', name: 'dismissible', label: 'Pode ser fechada', valueTrue: true, valueFalse: false },
        ],
      },
      announcementPreview,
    ),
  )

  Components.addType(
    COMPONENT_TYPES.FILTER_BAR,
    propsType(
      COMPONENT_TYPES.FILTER_BAR,
      {
        tagName: 'div',
        name: 'Barra de filtros',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [
          { type: 'checkbox', name: 'show_categories', label: 'Mostrar categorias', valueTrue: true, valueFalse: false },
          { type: 'checkbox', name: 'show_sort', label: 'Mostrar ordenação', valueTrue: true, valueFalse: false },
        ],
      },
      (props) => filterBarPreview(props, getData()),
    ),
  )

  Components.addType(
    COMPONENT_TYPES.SEARCH,
    propsType(
      COMPONENT_TYPES.SEARCH,
      {
        tagName: 'div',
        name: 'Busca',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [{ type: 'text', name: 'placeholder', label: 'Texto de dica' }],
      },
      searchPreview,
    ),
  )

  Components.addType(
    COMPONENT_TYPES.OPENING_HOURS,
    propsType(
      COMPONENT_TYPES.OPENING_HOURS,
      {
        tagName: 'div',
        name: 'Horários',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [
          {
            type: 'checkbox',
            name: 'highlight_today',
            label: 'Destacar o dia de hoje',
            valueTrue: true,
            valueFalse: false,
          },
        ],
      },
      (props) => openingHoursPreview(props, getData()),
    ),
  )

  Components.addType(
    COMPONENT_TYPES.RESTAURANT_INFO,
    propsType(
      COMPONENT_TYPES.RESTAURANT_INFO,
      {
        tagName: 'div',
        name: 'Informações do restaurante',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [
          { type: 'checkbox', name: 'show_address', label: 'Mostrar endereço', valueTrue: true, valueFalse: false },
          { type: 'checkbox', name: 'show_phone', label: 'Mostrar telefone', valueTrue: true, valueFalse: false },
          { type: 'checkbox', name: 'show_map', label: 'Mostrar mapa', valueTrue: true, valueFalse: false },
        ],
      },
      (props) => restaurantInfoPreview(props, getData()),
    ),
  )

  Components.addType(
    COMPONENT_TYPES.DELIVERY_INFO,
    propsType(
      COMPONENT_TYPES.DELIVERY_INFO,
      {
        tagName: 'div',
        name: 'Entrega',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [{ type: 'checkbox', name: 'show_fee', label: 'Mostrar taxa', valueTrue: true, valueFalse: false }],
      },
      (props) => deliveryPreview(props, getData()),
    ),
  )

  Components.addType(
    COMPONENT_TYPES.PAYMENT_METHODS,
    propsType(
      COMPONENT_TYPES.PAYMENT_METHODS,
      {
        tagName: 'div',
        name: 'Formas de pagamento',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [],
      },
      (props) => paymentMethodsPreview(props, getData()),
    ),
  )

  Components.addType(
    COMPONENT_TYPES.SOCIAL_LINKS,
    propsType(
      COMPONENT_TYPES.SOCIAL_LINKS,
      {
        tagName: 'div',
        name: 'Redes sociais',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [
          { type: 'text', name: 'instagram', label: 'Instagram (URL)' },
          { type: 'text', name: 'facebook', label: 'Facebook (URL)' },
          { type: 'text', name: 'tiktok', label: 'TikTok (URL)' },
          { type: 'text', name: 'x', label: 'X (URL)' },
          { type: 'text', name: 'youtube', label: 'YouTube (URL)' },
        ],
      },
      socialLinksPreview,
    ),
  )

  Components.addType(
    COMPONENT_TYPES.WHATSAPP_BUTTON,
    propsType(
      COMPONENT_TYPES.WHATSAPP_BUTTON,
      {
        tagName: 'div',
        name: 'Botão de WhatsApp',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [
          { type: 'text', name: 'label', label: 'Texto do botão' },
          // Vazio usa o telefone do cadastro do restaurante — o caso comum.
          { type: 'text', name: 'phone', label: 'Telefone (vazio = o do cadastro)' },
          { type: 'text', name: 'message', label: 'Mensagem inicial' },
          {
            type: 'select',
            name: 'position',
            label: 'Posição',
            options: [
              { id: 'floating', name: 'Flutuando no canto' },
              { id: 'inline', name: 'Dentro da página' },
            ],
          },
        ],
      },
      whatsappPreview,
    ),
  )

  // Sem prévia própria: o mapa depende de um serviço externo que não faz
  // sentido carregar dentro do canvas, e um contêiner vazio precisa de algo
  // clicável para o cliente conseguir selecioná-lo.
  Components.addType(COMPONENT_TYPES.MAP, {
    model: {
      defaults: {
        tagName: 'div',
        name: 'Mapa',
        droppable: false,
        editable: false,
        content: placeholder('Mapa', 'Aparece no site publicado'),
        stylable: BOX_STYLES,
      },
    },
  })

  // O rodapé tem configuração de verdade: duas colunas de links, cada uma
  // apontando para um MENU pelo slug — o mesmo mecanismo do cabeçalho. É o que
  // permite ao restaurante acrescentar "Política de privacidade", "Termos de
  // uso" ou "Contato" mais tarde, sem tocar em código.
  Components.addType(
    COMPONENT_TYPES.FOOTER,
    propsType(
      COMPONENT_TYPES.FOOTER,
      {
        tagName: 'footer',
        name: 'Rodapé',
        droppable: false,
        editable: false,
        stylable: BOX_STYLES,
        traits: [
          { type: 'checkbox', name: 'show_social', label: 'Mostrar redes sociais', valueTrue: true, valueFalse: false },
          {
            type: 'checkbox',
            name: 'show_payment_methods',
            label: 'Mostrar formas de pagamento',
            valueTrue: true,
            valueFalse: false,
          },
          { type: 'text', name: 'link_menu_1_title', label: 'Coluna 1 — título' },
          { type: 'text', name: 'link_menu_1', label: 'Coluna 1 — menu (slug)' },
          { type: 'text', name: 'link_menu_2_title', label: 'Coluna 2 — título' },
          { type: 'text', name: 'link_menu_2', label: 'Coluna 2 — menu (slug)' },
          { type: 'text', name: 'link_menu_3_title', label: 'Coluna 3 — título' },
          { type: 'text', name: 'link_menu_3', label: 'Coluna 3 — menu (slug)' },
        ],
      },
      (props) => footerPreview(props, getData()),
    ),
  )
}
