/**
 * Registry do renderer: tipo de bloco → componente Vue.
 *
 * É o mapa que o site público usa para desenhar o schema compilado. Nada de
 * GrapesJS aqui — este arquivo é importado pelo bundle que o cliente final
 * baixa, e é justamente o que permite o cardápio abrir rápido no celular.
 *
 * Tipo que não estiver no mapa não é renderizado (o `SfNode` ignora). Fail
 * closed de novo: um bloco que o renderer não conhece não tem como desenhar
 * certo, e um espaço vazio é mais fácil de diagnosticar do que um layout
 * sutilmente errado.
 */
import { COMPONENT_TYPES } from './components'

export const RENDERER_REGISTRY: Record<string, string> = {
  // Layout — todos caem no mesmo componente-caixa, que só aplica tag, classes
  // e filhos. O que os diferencia visualmente é o CSS que o cliente montou no
  // editor, não código nosso.
  [COMPONENT_TYPES.SECTION]: 'SfBox',
  [COMPONENT_TYPES.CONTAINER]: 'SfBox',
  [COMPONENT_TYPES.ROW]: 'SfBox',
  [COMPONENT_TYPES.COLUMN]: 'SfBox',
  [COMPONENT_TYPES.SPACER]: 'SfSpacer',
  [COMPONENT_TYPES.DIVIDER]: 'SfDivider',
  wrapper: 'SfBox',

  // Conteúdo
  [COMPONENT_TYPES.HEADING]: 'SfHeading',
  [COMPONENT_TYPES.TEXT]: 'SfText',
  text: 'SfText',
  textnode: 'SfText',
  [COMPONENT_TYPES.IMAGE]: 'SfImage',
  [COMPONENT_TYPES.ICON]: 'SfText',
  [COMPONENT_TYPES.BUTTON]: 'SfButton',
  [COMPONENT_TYPES.LINK]: 'SfButton',
  [COMPONENT_TYPES.LIST]: 'SfBox',
  [COMPONENT_TYPES.SOCIAL_LINKS]: 'SfSocialLinks',
  [COMPONENT_TYPES.BADGE]: 'SfBadge',
  [COMPONENT_TYPES.RATING]: 'SfRating',

  // Estrutura de página
  [COMPONENT_TYPES.HERO]: 'HeroSection',
  [COMPONENT_TYPES.BANNER]: 'SfBox',
  [COMPONENT_TYPES.ANNOUNCEMENT_BAR]: 'SfAnnouncementBar',
  [COMPONENT_TYPES.FILTER_BAR]: 'SfFilterBar',
  [COMPONENT_TYPES.FOOTER]: 'SfFooter',
  // `sf-header` sai daqui de propósito: o cabeçalho passou a ser do SITE
  // (`MenuSite.header`) e é desenhado pelo `StorefrontHeader`, fora da página.
  // Uma página antiga que ainda tenha o bloco simplesmente não o desenha — o
  // contrário daria DOIS cabeçalhos empilhados.

  // Cardápio (dados reais da API)
  [COMPONENT_TYPES.CATEGORIES]: 'SfCategories',
  [COMPONENT_TYPES.PRODUCT_GRID]: 'SfProductGrid',
  [COMPONENT_TYPES.PRODUCT_CAROUSEL]: 'SfProductGrid',
  [COMPONENT_TYPES.FEATURED_PRODUCTS]: 'SfProductGrid',
  [COMPONENT_TYPES.PROMOTIONS]: 'SfProductGrid',
  [COMPONENT_TYPES.SEARCH]: 'SfSearch',

  // Restaurante
  [COMPONENT_TYPES.RESTAURANT_INFO]: 'SfRestaurantInfo',
  [COMPONENT_TYPES.OPENING_HOURS]: 'SfOpeningHours',
  [COMPONENT_TYPES.DELIVERY_INFO]: 'SfDeliveryInfo',
  [COMPONENT_TYPES.PAYMENT_METHODS]: 'SfPaymentMethods',
  [COMPONENT_TYPES.WHATSAPP_BUTTON]: 'SfWhatsappButton',
  [COMPONENT_TYPES.CART_BUTTON]: 'SfButton',
  [COMPONENT_TYPES.MAP]: 'SfBox',
}

export function componentNameFor(type: string): string | null {
  return RENDERER_REGISTRY[type] ?? null
}
