/**
 * Blocos arrastáveis do painel.
 *
 * Um bloco é só um atalho que cria um componente — nunca um pedaço de HTML
 * solto. HTML dentro do bloco significaria que a lógica do componente estaria
 * duplicada em dois lugares, e que uma correção no componente não alcançaria as
 * páginas montadas antes dela.
 */
import type { Editor } from 'grapesjs'
import { materialIconMarkup, type MaterialIconName } from '../../icons/material-icons'
import { COMPONENT_TYPES } from '../registry/components'

const CATEGORY_SECTIONS = 'Seções prontas'
const CATEGORY_LAYOUT = 'Layout'
const CATEGORY_CONTENT = 'Conteúdo'
const CATEGORY_MENU = 'Cardápio'
const CATEGORY_RESTAURANT = 'Restaurante'

/** Seção pronta vinda do backend (mesma peça que monta a home padrão). */
export interface SectionPreset {
  key: string
  label: string
  component: Record<string, unknown>
}

interface BlockSpec {
  id: string
  label: string
  category: string
  content: Record<string, unknown>
  icon: MaterialIconName
}

/**
 * Um ícone por seção pronta, pela CHAVE que o backend usa (`starter.py` →
 * `SECTION_LIBRARY`). É a mesma família de ícone do bloco equivalente na
 * lista estática abaixo — a "Vitrine de produtos" arrastada como seção pronta
 * ou como bloco avulso mostra o mesmo `grid_view`, e não dois ícones
 * diferentes para a mesma coisa.
 */
const SECTION_ICONS: Record<string, MaterialIconName> = {
  hero: 'panorama',
  categories: 'category',
  'product-grid': 'grid_view',
  promotions: 'local_offer',
  info: 'info',
  footer: 'vertical_align_bottom',
  whatsapp: 'chat',
}

/**
 * Seção > contêiner > componente: a estrutura que o projeto assume em todo
 * lugar (renderer, compiler e CSS). Um bloco de conteúdo solto na raiz ficaria
 * sem a largura máxima do site e encostaria na borda da tela.
 */
function section(children: Record<string, unknown>[]): Record<string, unknown> {
  return {
    type: COMPONENT_TYPES.SECTION,
    components: [{ type: COMPONENT_TYPES.CONTAINER, components: children }],
  }
}

const BLOCKS: BlockSpec[] = [
  {
    id: 'sf-block-section',
    icon: 'view_agenda',
    label: 'Seção',
    category: CATEGORY_LAYOUT,
    content: section([]),
  },
  {
    id: 'sf-block-two-columns',
    icon: 'view_column',
    label: '2 Colunas',
    category: CATEGORY_LAYOUT,
    content: section([
      {
        type: COMPONENT_TYPES.ROW,
        style: { display: 'flex', gap: '24px', 'flex-wrap': 'wrap' },
        components: [
          { type: COMPONENT_TYPES.COLUMN, style: { flex: '1 1 320px' } },
          { type: COMPONENT_TYPES.COLUMN, style: { flex: '1 1 320px' } },
        ],
      },
    ]),
  },
  {
    id: 'sf-block-spacer',
    icon: 'height',
    label: 'Espaço',
    category: CATEGORY_LAYOUT,
    content: { type: COMPONENT_TYPES.SPACER },
  },
  {
    id: 'sf-block-divider',
    icon: 'horizontal_rule',
    label: 'Divisória',
    category: CATEGORY_LAYOUT,
    content: { type: COMPONENT_TYPES.DIVIDER },
  },

  {
    id: 'sf-block-heading',
    icon: 'title',
    label: 'Título',
    category: CATEGORY_CONTENT,
    content: { type: COMPONENT_TYPES.HEADING },
  },
  {
    id: 'sf-block-text',
    icon: 'notes',
    label: 'Texto',
    category: CATEGORY_CONTENT,
    content: { type: COMPONENT_TYPES.TEXT },
  },
  {
    id: 'sf-block-image',
    icon: 'image',
    label: 'Imagem',
    category: CATEGORY_CONTENT,
    content: { type: COMPONENT_TYPES.IMAGE },
  },
  {
    id: 'sf-block-button',
    icon: 'smart_button',
    label: 'Botão',
    category: CATEGORY_CONTENT,
    content: { type: COMPONENT_TYPES.BUTTON },
  },
  {
    id: 'sf-block-hero',
    icon: 'panorama',
    label: 'Capa',
    category: CATEGORY_CONTENT,
    // Bloco de configuração, sem filhos: os mesmos campos que o backend usa na
    // home padrão (ver `starter.py`). Se divergirem, a capa arrastada aqui sai
    // diferente da que o site já nasceu com.
    content: {
      type: COMPONENT_TYPES.HERO,
      props: {
        title: 'Peça hoje e receba em casa',
        highlight: 'sem taxa',
        description: 'Produtos fresquinhos, escolhidos na hora e entregues na sua porta.',
        cta_label: 'Ver cardápio',
        cta_url: '#cardapio',
        image: '',
        image_position: 'right-bottom',
        image_width: '52%',
        height: '350px',
        height_tablet: '300px',
        height_mobile: '520px',
        align: 'left',
        align_mobile: 'center',
        padding: '56px',
        padding_mobile: '32px',
        background: '',
        decorations: true,
      },
      style: { margin: '20px auto 0', 'max-width': 'var(--sf-container-width)' },
    },
  },

  {
    id: 'sf-block-announcement',
    icon: 'campaign',
    label: 'Faixa de aviso',
    category: CATEGORY_CONTENT,
    content: { type: COMPONENT_TYPES.ANNOUNCEMENT_BAR },
  },
  {
    id: 'sf-block-badge',
    icon: 'sell',
    label: 'Selo',
    category: CATEGORY_CONTENT,
    content: { type: COMPONENT_TYPES.BADGE },
  },
  {
    id: 'sf-block-rating',
    icon: 'star',
    label: 'Nota',
    category: CATEGORY_CONTENT,
    content: { type: COMPONENT_TYPES.RATING },
  },
  {
    id: 'sf-block-filter-bar',
    icon: 'filter_list',
    label: 'Barra de filtros',
    category: CATEGORY_MENU,
    content: section([{ type: COMPONENT_TYPES.FILTER_BAR }]),
  },
  {
    id: 'sf-block-categories',
    icon: 'category',
    label: 'Categorias',
    category: CATEGORY_MENU,
    content: section([{ type: COMPONENT_TYPES.CATEGORIES }]),
  },
  {
    id: 'sf-block-product-grid',
    icon: 'grid_view',
    label: 'Vitrine de produtos',
    category: CATEGORY_MENU,
    content: section([{ type: COMPONENT_TYPES.PRODUCT_GRID }]),
  },
  {
    id: 'sf-block-featured',
    icon: 'auto_awesome',
    label: 'Destaques',
    category: CATEGORY_MENU,
    // Destaques nasce em carrossel: é uma seleção curta que fica melhor
    // correndo para o lado do que numa grade com uma linha só.
    content: section([{ type: COMPONENT_TYPES.FEATURED_PRODUCTS, props: { layout: 'carousel' } }]),
  },
  {
    id: 'sf-block-product-carousel',
    icon: 'view_column',
    label: 'Carrossel de produtos',
    category: CATEGORY_MENU,
    content: section([{ type: COMPONENT_TYPES.PRODUCT_CAROUSEL, props: { layout: 'carousel' } }]),
  },
  {
    id: 'sf-block-promotions',
    icon: 'local_offer',
    label: 'Promoções',
    category: CATEGORY_MENU,
    content: section([{ type: COMPONENT_TYPES.PROMOTIONS }]),
  },
  {
    id: 'sf-block-search',
    icon: 'search',
    label: 'Busca',
    category: CATEGORY_MENU,
    content: section([{ type: COMPONENT_TYPES.SEARCH }]),
  },

  {
    id: 'sf-block-restaurant-info',
    icon: 'info',
    label: 'Informações',
    category: CATEGORY_RESTAURANT,
    content: section([{ type: COMPONENT_TYPES.RESTAURANT_INFO }]),
  },
  {
    id: 'sf-block-opening-hours',
    icon: 'schedule',
    label: 'Horários',
    category: CATEGORY_RESTAURANT,
    content: section([{ type: COMPONENT_TYPES.OPENING_HOURS }]),
  },
  {
    id: 'sf-block-delivery',
    icon: 'local_shipping',
    label: 'Entrega',
    category: CATEGORY_RESTAURANT,
    content: section([{ type: COMPONENT_TYPES.DELIVERY_INFO }]),
  },
  {
    id: 'sf-block-payments',
    icon: 'payments',
    label: 'Pagamentos',
    category: CATEGORY_RESTAURANT,
    content: section([{ type: COMPONENT_TYPES.PAYMENT_METHODS }]),
  },
  {
    id: 'sf-block-footer',
    icon: 'vertical_align_bottom',
    label: 'Rodapé',
    category: CATEGORY_RESTAURANT,
    content: {
      type: COMPONENT_TYPES.FOOTER,
      props: {
        show_social: true,
        show_payment_methods: true,
        link_menu_1_title: 'Institucional',
        link_menu_1: '',
        link_menu_2_title: 'Atendimento',
        link_menu_2: '',
        link_menu_3_title: 'Cardápio',
        link_menu_3: '',
      },
    },
  },
  {
    id: 'sf-block-whatsapp',
    icon: 'chat',
    label: 'WhatsApp',
    category: CATEGORY_RESTAURANT,
    content: { type: COMPONENT_TYPES.WHATSAPP_BUTTON },
  },
]

export function registerBlocks(editor: Editor, sections: SectionPreset[] = []): void {
  // As SEÇÕES PRONTAS vêm primeiro no painel: é o que o cliente arrasta para
  // montar uma página inteira em minutos. São as mesmas peças da home padrão,
  // servidas pelo backend (`GET /api/v1/storefront/schema/` → `sections`), e
  // não uma segunda cópia aqui — uma cópia divergiria na primeira correção.
  for (const preset of sections) {
    const icon = SECTION_ICONS[preset.key]
    editor.Blocks.add(`sf-section-${preset.key}`, {
      label: preset.label,
      category: CATEGORY_SECTIONS,
      content: preset.component,
      select: true,
      // Sem ícone o card do bloco mostrava só texto — o painel inteiro virava
      // uma lista de retângulos brancos indistinguíveis até o cliente ler
      // cada rótulo. O ícone é reconhecido antes da palavra.
      media: icon ? materialIconMarkup(icon, 28) : undefined,
    })
  }

  for (const block of BLOCKS) {
    editor.Blocks.add(block.id, {
      label: block.label,
      category: block.category,
      content: block.content,
      select: true,
      media: materialIconMarkup(block.icon, 28),
    })
  }
}
