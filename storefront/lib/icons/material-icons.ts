/**
 * Ícones — uma fonte só, usada no site publicado E no editor.
 *
 * Antes, cada ícone era desenhado à mão (`<svg><path stroke="..."/></svg>`
 * repetido em cada componente) ou virava emoji dentro das prévias do canvas
 * (🛒, 👤, ⌕). Isso divergia sozinho: o carrinho do cabeçalho tinha um traço
 * e a prévia do mesmo botão dentro do editor tinha outro.
 *
 * Aqui entra o Material Symbols (`@material-design-icons/svg`, o pacote
 * oficial do Google só com os arquivos SVG — sem framework, sem fonte de
 * ícone por ligatura). Cada ícone é importado como TEXTO (`?raw`) e SÓ os
 * ícones realmente usados entram no bundle — o Vite não empacota o pacote
 * inteiro, só o que está `import`ado aqui por nome.
 *
 * O arquivo original vem com `fill` implícito (herda preto do navegador); o
 * `d` do `<path>` é extraído uma vez, na importação, e quem desenha o ícone
 * (`MaterialIcon.vue` no Vue, `materialIconMarkup` no HTML puro das prévias)
 * aplica `fill="currentColor"` — o mesmo princípio que os ícones desenhados à
 * mão já seguiam: a cor vem de fora, do texto ao redor.
 */
import arrowForward from '@material-design-icons/svg/outlined/arrow_forward.svg?raw'
import autoAwesome from '@material-design-icons/svg/outlined/auto_awesome.svg?raw'
import campaign from '@material-design-icons/svg/outlined/campaign.svg?raw'
import category from '@material-design-icons/svg/outlined/category.svg?raw'
import chat from '@material-design-icons/svg/outlined/chat.svg?raw'
import chevronLeft from '@material-design-icons/svg/outlined/chevron_left.svg?raw'
import chevronRight from '@material-design-icons/svg/outlined/chevron_right.svg?raw'
import close from '@material-design-icons/svg/outlined/close.svg?raw'
import description from '@material-design-icons/svg/outlined/description.svg?raw'
import expandLess from '@material-design-icons/svg/outlined/expand_less.svg?raw'
import expandMore from '@material-design-icons/svg/outlined/expand_more.svg?raw'
import filterList from '@material-design-icons/svg/outlined/filter_list.svg?raw'
import gridView from '@material-design-icons/svg/outlined/grid_view.svg?raw'
import height from '@material-design-icons/svg/outlined/height.svg?raw'
import horizontalRule from '@material-design-icons/svg/outlined/horizontal_rule.svg?raw'
import image from '@material-design-icons/svg/outlined/image.svg?raw'
import info from '@material-design-icons/svg/outlined/info.svg?raw'
import layers from '@material-design-icons/svg/outlined/layers.svg?raw'
import link from '@material-design-icons/svg/outlined/link.svg?raw'
import list from '@material-design-icons/svg/outlined/list.svg?raw'
import localOffer from '@material-design-icons/svg/outlined/local_offer.svg?raw'
import localShipping from '@material-design-icons/svg/outlined/local_shipping.svg?raw'
import locationOn from '@material-design-icons/svg/outlined/location_on.svg?raw'
import notes from '@material-design-icons/svg/outlined/notes.svg?raw'
import palette from '@material-design-icons/svg/outlined/palette.svg?raw'
import panorama from '@material-design-icons/svg/outlined/panorama.svg?raw'
import payments from '@material-design-icons/svg/outlined/payments.svg?raw'
import person from '@material-design-icons/svg/outlined/person.svg?raw'
import publish from '@material-design-icons/svg/outlined/publish.svg?raw'
import redo from '@material-design-icons/svg/outlined/redo.svg?raw'
import save from '@material-design-icons/svg/outlined/save.svg?raw'
import schedule from '@material-design-icons/svg/outlined/schedule.svg?raw'
import search from '@material-design-icons/svg/outlined/search.svg?raw'
import sell from '@material-design-icons/svg/outlined/sell.svg?raw'
import shoppingCart from '@material-design-icons/svg/outlined/shopping_cart.svg?raw'
import smartButton from '@material-design-icons/svg/outlined/smart_button.svg?raw'
import star from '@material-design-icons/svg/outlined/star.svg?raw'
import title from '@material-design-icons/svg/outlined/title.svg?raw'
import tune from '@material-design-icons/svg/outlined/tune.svg?raw'
import undo from '@material-design-icons/svg/outlined/undo.svg?raw'
import verticalAlignBottom from '@material-design-icons/svg/outlined/vertical_align_bottom.svg?raw'
import viewAgenda from '@material-design-icons/svg/outlined/view_agenda.svg?raw'
import viewColumn from '@material-design-icons/svg/outlined/view_column.svg?raw'
import viewHeadline from '@material-design-icons/svg/outlined/view_headline.svg?raw'
import visibility from '@material-design-icons/svg/outlined/visibility.svg?raw'
import widgets from '@material-design-icons/svg/outlined/widgets.svg?raw'

const RAW = {
  arrow_forward: arrowForward,
  auto_awesome: autoAwesome,
  campaign,
  category,
  chat,
  chevron_left: chevronLeft,
  chevron_right: chevronRight,
  close,
  description,
  expand_less: expandLess,
  expand_more: expandMore,
  filter_list: filterList,
  grid_view: gridView,
  height,
  horizontal_rule: horizontalRule,
  image,
  info,
  layers,
  link,
  list,
  local_offer: localOffer,
  local_shipping: localShipping,
  location_on: locationOn,
  notes,
  palette,
  panorama,
  payments,
  person,
  publish,
  redo,
  save,
  schedule,
  search,
  sell,
  shopping_cart: shoppingCart,
  smart_button: smartButton,
  star,
  title,
  tune,
  undo,
  vertical_align_bottom: verticalAlignBottom,
  view_agenda: viewAgenda,
  view_column: viewColumn,
  view_headline: viewHeadline,
  visibility,
  widgets,
} as const

export type MaterialIconName = keyof typeof RAW

export const MATERIAL_ICON_NAMES = Object.keys(RAW) as MaterialIconName[]

/** Todo ícone do pacote é um `<svg viewBox="0 0 24 24"><path d="…"/></svg>` só. */
function extractPath(svg: string): string {
  return svg.match(/<path d="([^"]+)"/)?.[1] ?? ''
}

const PATHS = Object.fromEntries(
  Object.entries(RAW).map(([name, svg]) => [name, extractPath(svg)]),
) as Record<MaterialIconName, string>

/** O `d` do ícone — o que `MaterialIcon.vue` usa para desenhar via `<path>`. */
export function materialIconPath(name: MaterialIconName): string {
  return PATHS[name] ?? ''
}

/**
 * Markup pronto, para os dois lugares que não montam componente Vue: as
 * prévias do canvas do editor (HTML puro, montado como string) e o ícone de
 * cada bloco no painel de Blocos (campo `media` do GrapesJS).
 */
export function materialIconMarkup(name: MaterialIconName, size: number | string = 20): string {
  const d = PATHS[name]
  if (!d) return ''
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="currentColor" aria-hidden="true" focusable="false"><path d="${d}"/></svg>`
}
