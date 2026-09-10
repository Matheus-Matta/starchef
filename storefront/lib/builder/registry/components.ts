/**
 * Registro central de tipos de componente.
 *
 * Uma lista só, usada pelo editor (registro de tipos e blocos), pelo compiler
 * (o que sobrevive à compilação) e pelo renderer (o que sabe desenhar). Três
 * listas separadas divergiriam, e a divergência aparece do pior jeito: o
 * cliente monta a página, salva, e o site público mostra um buraco.
 *
 * O prefixo `sf-` evita colisão com os tipos nativos do GrapesJS (`text`,
 * `image`, `link`…), que têm registro global. Os mesmos nomes valem no backend
 * — `GET /api/v1/storefront/schema/` devolve a allowlist de lá, e é ela que
 * manda: o que não estiver na lista do servidor é recusado ao salvar.
 */

export const COMPONENT_TYPES = {
  // Layout
  SECTION: 'sf-section',
  CONTAINER: 'sf-container',
  ROW: 'sf-row',
  COLUMN: 'sf-column',
  SPACER: 'sf-spacer',
  DIVIDER: 'sf-divider',

  // Conteúdo
  HEADING: 'sf-heading',
  TEXT: 'sf-text',
  IMAGE: 'sf-image',
  ICON: 'sf-icon',
  BUTTON: 'sf-button',
  LINK: 'sf-link',
  LIST: 'sf-list',
  SOCIAL_LINKS: 'sf-social-links',
  BADGE: 'sf-badge',
  RATING: 'sf-rating',

  // Cardápio e restaurante (dados reais vindos da API)
  HERO: 'sf-hero',
  BANNER: 'sf-banner',
  ANNOUNCEMENT_BAR: 'sf-announcement-bar',
  FILTER_BAR: 'sf-filter-bar',
  CATEGORIES: 'sf-categories',
  PRODUCT_GRID: 'sf-product-grid',
  PRODUCT_CAROUSEL: 'sf-product-carousel',
  FEATURED_PRODUCTS: 'sf-featured-products',
  PROMOTIONS: 'sf-promotions',
  RESTAURANT_INFO: 'sf-restaurant-info',
  OPENING_HOURS: 'sf-opening-hours',
  DELIVERY_INFO: 'sf-delivery-info',
  PAYMENT_METHODS: 'sf-payment-methods',
  SEARCH: 'sf-search',
  CART_BUTTON: 'sf-cart-button',
  WHATSAPP_BUTTON: 'sf-whatsapp-button',
  MAP: 'sf-map',
  HEADER: 'sf-header',
  FOOTER: 'sf-footer',
} as const

export type ComponentType = (typeof COMPONENT_TYPES)[keyof typeof COMPONENT_TYPES]

export const ALL_COMPONENT_TYPES: string[] = Object.values(COMPONENT_TYPES)

/** Tipos nativos do GrapesJS que também podem aparecer no projeto salvo. */
export const BUILTIN_TYPES = ['wrapper', 'text', 'textnode'] as const

/** Blocos que não aceitam filhos — o editor bloqueia o drop dentro deles. */
export const LEAF_TYPES: string[] = [
  COMPONENT_TYPES.HEADING,
  COMPONENT_TYPES.TEXT,
  COMPONENT_TYPES.IMAGE,
  COMPONENT_TYPES.ICON,
  COMPONENT_TYPES.SPACER,
  COMPONENT_TYPES.DIVIDER,
  COMPONENT_TYPES.CATEGORIES,
  COMPONENT_TYPES.PRODUCT_GRID,
  COMPONENT_TYPES.PRODUCT_CAROUSEL,
  COMPONENT_TYPES.FEATURED_PRODUCTS,
  COMPONENT_TYPES.PROMOTIONS,
  COMPONENT_TYPES.RESTAURANT_INFO,
  COMPONENT_TYPES.OPENING_HOURS,
  COMPONENT_TYPES.DELIVERY_INFO,
  COMPONENT_TYPES.PAYMENT_METHODS,
  COMPONENT_TYPES.SEARCH,
  COMPONENT_TYPES.MAP,
  COMPONENT_TYPES.ANNOUNCEMENT_BAR,
  COMPONENT_TYPES.FILTER_BAR,
  COMPONENT_TYPES.BADGE,
  COMPONENT_TYPES.RATING,
  // A capa virou bloco de configuração: título, botão e imagem são props, não
  // filhos que se possa arrastar para fora e deixar a capa sem chamada.
  COMPONENT_TYPES.HERO,
]

/** Tag HTML padrão de cada tipo, quando o projeto não trouxer uma. */
export const DEFAULT_TAGS: Record<string, string> = {
  [COMPONENT_TYPES.SECTION]: 'section',
  [COMPONENT_TYPES.CONTAINER]: 'div',
  [COMPONENT_TYPES.ROW]: 'div',
  [COMPONENT_TYPES.COLUMN]: 'div',
  [COMPONENT_TYPES.SPACER]: 'div',
  [COMPONENT_TYPES.DIVIDER]: 'hr',
  [COMPONENT_TYPES.HEADING]: 'h2',
  [COMPONENT_TYPES.TEXT]: 'p',
  [COMPONENT_TYPES.IMAGE]: 'img',
  [COMPONENT_TYPES.ICON]: 'span',
  [COMPONENT_TYPES.BUTTON]: 'a',
  [COMPONENT_TYPES.LINK]: 'a',
  [COMPONENT_TYPES.LIST]: 'ul',
  [COMPONENT_TYPES.HEADER]: 'header',
  [COMPONENT_TYPES.FOOTER]: 'footer',
  [COMPONENT_TYPES.ANNOUNCEMENT_BAR]: 'div',
  [COMPONENT_TYPES.FILTER_BAR]: 'div',
  [COMPONENT_TYPES.BADGE]: 'span',
  [COMPONENT_TYPES.RATING]: 'span',
  [COMPONENT_TYPES.HERO]: 'section',
  [COMPONENT_TYPES.BANNER]: 'section',
  wrapper: 'div',
  text: 'p',
}
