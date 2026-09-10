/**
 * Como cada bloco se DESENHA dentro do canvas do editor.
 *
 * O site público é Vue; o canvas do GrapesJS é um iframe de HTML puro. Rodar o
 * renderer Vue lá dentro significaria embarcar o app inteiro no editor, e é
 * justamente o que a arquitetura evita ("GrapesJS edita, Nuxt renderiza").
 *
 * **O canvas desenha os dados REAIS do restaurante.** Antes ele inventava
 * ("Produto em destaque", "Primeiro link") e o site publicava outra coisa —
 * pior que a diferença de texto era a de estrutura: uma vitrine sem produto
 * nenhum aparecia cheia no editor e sumia no site, então o cliente montava a
 * página sobre uma ilusão.
 *
 * Duas decisões sustentam a fidelidade:
 *
 * - **O payload é o mesmo.** O editor busca `/public/storefront/<slug>/`, o
 *   mesmo endereço que o site usa, e entrega esse payload às funções daqui.
 * - **A regra é a mesma.** O que cada bloco mostra é decidido em
 *   `lib/storefront/resolve`, chamado tanto pelos componentes Vue quanto por
 *   estas funções. Duas implementações da mesma regra divergem sempre; uma só
 *   não tem como.
 *
 * O que continua sendo aproximação é só o COMPORTAMENTO: as setas do carrossel
 * não rolam e o filtro não filtra. O canvas é uma fotografia da página, não a
 * página rodando.
 */
import { materialIconMarkup } from '~~/lib/icons/material-icons'
import {
  columnCount,
  formatPrice,
  propBool,
  propString,
  resolveCategories,
  resolveFooterColumns,
  resolveHeroSlides,
  resolveShowcaseProducts,
  showcaseLayout,
} from '~~/lib/storefront/resolve'
import type { StorefrontPayload, StorefrontProduct } from '~~/types/storefront'

/**
 * A moldura que o componente Vue põe no PRÓPRIO nó.
 *
 * No site, `SfCategories` renderiza `<nav class="sf-categories">` — a classe
 * está no nó, não num filho. No canvas o nó é criado pelo GrapesJS e não tem
 * essa classe, então a prévia desenha a moldura por dentro. Sem isso as
 * etiquetas apareciam empilhadas no editor e lado a lado no site.
 */
type Props = Record<string, unknown>

// Os leitores de prop vêm do resolvedor — os mesmos que os componentes usam.
const str = (props: Props, key: string, fallback = '') => propString(props, key, fallback)
const bool = (props: Props, key: string, fallback = true) => propBool(props, key, fallback)

/** Escapa texto vindo de trait: o cliente digita, e isso vira HTML do canvas. */
export function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function placeholder(label: string, hint = '', modifier = ''): string {
  return `<div class="sf-canvas-placeholder${modifier}"><strong>${escapeHtml(label)}</strong>${
    hint ? `<span>${escapeHtml(hint)}</span>` : ''
  }</div>`
}

/** Aviso sem fundo, para não virar conteúdo por cima de uma área colorida. */
const ghost = (label: string, hint = '') => placeholder(label, hint, ' sf-canvas-placeholder--ghost')

/** Desconto em %, com a mesma guarda do site contra `Number(null) === 0`. */
function discountPercent(product: StorefrontProduct): number {
  if (!product.promotional_price) return 0
  const full = Number(product.price)
  const promo = Number(product.promotional_price)
  if (!Number.isFinite(full) || !Number.isFinite(promo) || full <= 0 || promo >= full) return 0
  return Math.round(((full - promo) / full) * 100)
}

function productCard(product: StorefrontProduct, props: Props): string {
  const showImage = bool(props, 'show_image')
  const showPrice = bool(props, 'show_price')
  const showOldPrice = bool(props, 'show_old_price')
  const showButton = bool(props, 'show_button')
  const showBadges = bool(props, 'show_badges')
  const showRating = bool(props, 'show_rating', false)
  const showDescription = bool(props, 'show_description', false)

  const off = discountPercent(product)
  const badges = showBadges
    ? `<div class="sf-product-card__badges">${
        off ? `<span class="sf-badge sf-badge--sale">-${off}%</span>` : ''
      }${product.is_weighed ? '<span class="sf-badge sf-badge--info">por kg</span>' : ''}${
        product.available_for_delivery ? '' : '<span class="sf-badge sf-badge--muted">só retirada</span>'
      }</div>`
    : ''

  // A moldura da mídia existe sempre, como no componente: é ela que reserva a
  // proporção do cartão. Só a imagem depende de "mostrar foto".
  const image = showImage
    ? product.image
      ? `<img class="sf-product-card__image" src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" loading="lazy">`
      : '<div class="sf-product-card__image sf-product-card__image--empty"></div>'
    : ''
  const media = `<div class="sf-product-card__media">${image}${badges}</div>`

  return `
    <article class="sf-product-card sf-product-card--${escapeHtml(str(props, 'card_style', 'market'))}">
      ${media}
      <div class="sf-product-card__body">
        <h3 class="sf-product-card__name">${escapeHtml(product.name)}</h3>
        ${showDescription && product.description ? `<p class="sf-product-card__description">${escapeHtml(product.description)}</p>` : ''}
        ${showRating ? `<div class="sf-rating"><span class="sf-rating__star">${materialIconMarkup('star', 14)}</span><span class="sf-rating__value">${
          product.preparation_minutes ? `${product.preparation_minutes} min` : 'Novo'
        }</span></div>` : ''}
        <div class="sf-product-card__foot">
          ${showPrice
            ? `<div class="sf-product-card__price"><span>${formatPrice(product.current_price)}</span>${
                showOldPrice && product.promotional_price ? `<span class="sf-product-card__price-was">${formatPrice(product.price)}</span>` : ''
              }</div>`
            : '<span></span>'}
          ${showButton ? '<button type="button" class="sf-product-card__add">+</button>' : ''}
        </div>
      </div>
    </article>
  `
}

export function productGridPreview(props: Props, data: StorefrontPayload, nodeType: string): string {
  const products = resolveShowcaseProducts(data, props, nodeType)

  // Vitrine sem produto é desenhada VAZIA, com a mesma frase do site. Enchê-la
  // de exemplo era o pior dos defeitos antigos: o cliente montava a página
  // sobre uma seção que existia só no editor.
  if (!products.length) {
    return '<p class="sf-empty">Nenhum produto disponível nesta seção.</p>'
  }

  const cards = products.map((product) => productCard(product, props)).join('')
  const grid = [
    `--sf-grid-desktop:${columnCount(props, 'desktop', 4)}`,
    `--sf-grid-tablet:${columnCount(props, 'tablet', 2)}`,
    `--sf-grid-mobile:${columnCount(props, 'mobile', 2)}`,
  ].join(';')

  // As setas não rolam nada aqui — o canvas é uma fotografia, não a página
  // rodando —, mas mostram o formato, que é o que o cliente está decidindo.
  if (showcaseLayout(props, nodeType) === 'carousel') {
    return `
      <div class="sf-carousel">
        <button type="button" class="sf-carousel__arrow sf-carousel__arrow--prev" disabled>${materialIconMarkup('chevron_left', 20)}</button>
        <div class="sf-carousel__track" style="${grid}">${cards}</div>
        <button type="button" class="sf-carousel__arrow sf-carousel__arrow--next">${materialIconMarkup('chevron_right', 20)}</button>
      </div>
    `
  }

  return `<div class="sf-product-grid" style="${grid}">${cards}</div>`
}

export function categoriesPreview(props: Props, data: StorefrontPayload): string {
  const categories = resolveCategories(data, props)
  const chips = categories.length
    ? categories
        .map((category) => `<button type="button" class="sf-category-chip">${escapeHtml(category.name)}</button>`)
        .join('')
    : '<p class="sf-empty">Nenhuma categoria cadastrada ainda.</p>'
  const list = str(props, 'layout', 'chips') === 'list' ? ' sf-categories--list' : ''
  return `<div class="sf-categories${list}">${chips}</div>`
}

const SORT_LABELS: Record<string, string> = {
  default: 'Relevância',
  name: 'Nome (A-Z)',
  price_asc: 'Menor preço',
  price_desc: 'Maior preço',
}

export function filterBarPreview(props: Props, data: StorefrontPayload): string {
  const chips = bool(props, 'show_categories')
    ? `<div class="sf-filterbar__chips">
         <button type="button" class="sf-chip sf-chip--active">Todas as categorias</button>
         ${data.categories
           .filter((category) => !category.parent_id)
           .map((category) => `<button type="button" class="sf-chip">${escapeHtml(category.name)}</button>`)
           .join('')}
       </div>`
    : ''

  const configured = props.sort_options
  const keys = (Array.isArray(configured) && configured.length ? configured.map(String) : Object.keys(SORT_LABELS))
    .filter((key) => SORT_LABELS[key])

  const sort = bool(props, 'show_sort')
    ? `<label class="sf-filterbar__sort"><span>Ordenar por</span><select>${keys
        .map((key) => `<option>${escapeHtml(SORT_LABELS[key])}</option>`)
        .join('')}</select></label>`
    : ''

  return `<div class="sf-filterbar">${chips}${sort}</div>`
}

export function heroPreview(props: Props, data: StorefrontPayload): string {
  const slides = resolveHeroSlides(data, props)
  const slide = slides[0]
  const position = str(props, 'image_position', 'right-bottom')
  const side = position.startsWith('left') ? 'left' : 'right'
  const anchor = position.endsWith('center') ? 'center' : 'bottom'
  const align = str(props, 'align', 'left')
  const background = str(props, 'background')

  // As mesmas variáveis que o componente Vue define — é o que faz a prévia
  // respeitar altura, respiro e largura da imagem escolhidos nos traits.
  const vars = [
    `--sf-hero-height:${str(props, 'height', '350px')}`,
    `--sf-hero-padding:${str(props, 'padding', '56px')}`,
    `--sf-hero-image-width:${str(props, 'image_width', '52%')}`,
    background ? `--sf-hero-bg:${background}` : '',
  ].filter(Boolean).join(';')

  const media = slide?.image
    ? `<div class="sf-hero__media"><img src="${escapeHtml(slide.image)}" alt=""></div>`
    : `<div class="sf-hero__media">${ghost('Imagem da capa', 'Defina em "Imagem (URL)" ou vincule um menu de banners')}</div>`

  // Um ponto por banner de verdade — a quantidade que o site vai mostrar, e
  // não três fixos como antes. Com um banner só não há carrossel nenhum.
  const carousel = slides.length > 1
    ? `<button type="button" class="sf-hero__arrow sf-hero__arrow--prev">${materialIconMarkup('chevron_left', 20)}</button>
       <button type="button" class="sf-hero__arrow sf-hero__arrow--next">${materialIconMarkup('chevron_right', 20)}</button>
       <div class="sf-hero__dots">${slides
         .map((_, index) => `<button type="button" class="sf-hero__dot${index === 0 ? ' is-active' : ''}"></button>`)
         .join('')}</div>`
    : ''

  return `
    <section class="sf-hero sf-hero--image-${side} sf-hero--anchor-${anchor} sf-hero--align-${align}${slide?.image ? ' sf-hero--has-image' : ''}"
             style="${vars}">
      ${carousel}
      ${bool(props, 'decorations') ? '<div class="sf-hero__decor"><span class="sf-hero__circle sf-hero__circle--lg"></span><span class="sf-hero__circle sf-hero__circle--md"></span></div>' : ''}
      <div class="sf-hero__content">
        <h1 class="sf-hero__title">${escapeHtml(slide?.title ?? '')}${
          slide?.highlight ? ` <em class="sf-hero__highlight">${escapeHtml(slide.highlight)}</em>` : ''
        }</h1>
        ${slide?.description ? `<p class="sf-hero__description">${escapeHtml(slide.description)}</p>` : ''}
        ${slide?.ctaLabel ? `<span class="sf-hero__cta">${escapeHtml(slide.ctaLabel)} ${materialIconMarkup('arrow_forward', 16)}</span>` : ''}
      </div>
      ${media}
    </section>
  `
}

export function footerPreview(props: Props, data: StorefrontPayload): string {
  const columns = resolveFooterColumns(data, props)
    .map((column) => `<div class="sf-footer__col">
        <p class="sf-footer__col-title">${escapeHtml(column.title)}</p>
        <ul class="sf-footer__links">${column.items
          .map((item) => `<li><a>${escapeHtml(item.title)}</a></li>`)
          .join('')}</ul>
      </div>`)
    .join('')

  const payments = bool(props, 'show_payment_methods') && data.payment_methods.length
    ? `<div class="sf-footer__col">
         <p class="sf-footer__col-title">Formas de pagamento</p>
         <div style="display:flex;flex-wrap:wrap;gap:8px">${data.payment_methods
           .map((method) => `<span class="sf-badge">${escapeHtml(method.name)}</span>`)
           .join('')}</div>
       </div>`
    : ''

  const parts = data.restaurant.address
  const address = [parts.street, parts.district, parts.city].filter(Boolean).join(', ')

  return `
    <div class="sf-footer__inner">
      <div class="sf-footer__col">
        <strong>${escapeHtml(data.site.name || data.restaurant.name)}</strong>
        ${address ? `<p style="margin-top:6px;opacity:.8">${escapeHtml(address)}</p>` : ''}
        <p style="margin-top:6px;opacity:.6;font-size:13px">© ${new Date().getFullYear()}</p>
      </div>
      ${columns}
      ${payments}
    </div>
  `
}

export function searchPreview(props: Props): string {
  // Uma caixa desenhada, não um `<input>`: um campo de verdade dentro do
  // canvas roubaria o foco do editor e o cliente digitaria no site em vez de
  // na página. As medidas são as mesmas do `SfSearch`.
  return `<div style="width:100%;padding:12px 16px;border:1px solid var(--sf-border);
    border-radius:var(--sf-radius);background:var(--sf-background);color:var(--sf-muted-text);font-size:14px">${escapeHtml(
      str(props, 'placeholder', 'Buscar no cardápio...'),
    )}</div>`
}

const WEEKDAYS: Array<[string, string]> = [
  ['monday', 'Segunda'],
  ['tuesday', 'Terça'],
  ['wednesday', 'Quarta'],
  ['thursday', 'Quinta'],
  ['friday', 'Sexta'],
  ['saturday', 'Sábado'],
  ['sunday', 'Domingo'],
]

/** Mesma leitura tolerante do `SfOpeningHours`: string, `{open, close}` ou nada. */
function describeHours(value: unknown): string {
  if (!value) return 'Fechado'
  if (typeof value === 'string') return value
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    if (record.closed === true) return 'Fechado'
    if (record.open && record.close) return `${record.open} às ${record.close}`
  }
  return ''
}

export function openingHoursPreview(props: Props, data: StorefrontPayload): string {
  // A primeira unidade COM horário, não a primeira da lista — a mesma escolha
  // do componente, pelo mesmo motivo (filial recém-criada e ainda vazia).
  const branch = data.opening_hours.find((item) => item.hours && Object.keys(item.hours).length > 0)
  const hours = (branch?.hours ?? {}) as Record<string, unknown>
  const today = WEEKDAYS[(new Date().getDay() + 6) % 7]?.[0] ?? ''
  const highlight = bool(props, 'highlight_today')

  const rows = WEEKDAYS.map(([key, label]) => ({ key, label, value: describeHours(hours[key]) }))
    .filter((row) => row.value)
    .map((row) => `<div class="sf-hours__row${highlight && row.key === today ? ' sf-hours__row--today' : ''}">
        <span class="sf-hours__day">${row.label}</span>
        <span class="sf-hours__value">${escapeHtml(row.value)}</span>
      </div>`)
    .join('')

  return `<div class="sf-hours">${rows || '<p class="sf-empty">Horários ainda não cadastrados.</p>'}</div>`
}

export function restaurantInfoPreview(props: Props, data: StorefrontPayload): string {
  const parts = data.restaurant.address
  const address = [
    parts.street,
    parts.district,
    [parts.city, parts.state].filter(Boolean).join(' - '),
    parts.zip_code,
  ].filter(Boolean).join(', ')

  const card = (label: string, value: string) =>
    `<div class="sf-info-card"><div class="sf-info-card__label">${escapeHtml(label)}</div><div>${escapeHtml(value)}</div></div>`

  const cards = [
    bool(props, 'show_address') && address ? card('Endereço', address) : '',
    bool(props, 'show_phone') && data.restaurant.phone ? card('Telefone', data.restaurant.phone) : '',
    data.restaurant.email ? card('E-mail', data.restaurant.email) : '',
  ].join('')

  return cards
    ? `<div class="sf-info-grid">${cards}</div>`
    : placeholder('Endereço e contato', 'Preencha o cadastro do restaurante')
}

export function deliveryPreview(_props: Props, data: StorefrontPayload): string {
  const zones = data.delivery.zones
  if (!zones.length) {
    return '<p class="sf-empty">Este restaurante não faz entregas no momento.</p>'
  }
  const cards = zones
    .map((zone) => `<div class="sf-info-card">
        <div class="sf-info-card__label">${escapeHtml(zone.name)}</div>
        <div>Até ${escapeHtml(zone.max_radius_km)} km</div>
        <div>Taxa: ${escapeHtml(formatPrice(zone.delivery_fee) || 'grátis')}</div>
        <div>Aprox. ${escapeHtml(zone.estimated_minutes)} min</div>
      </div>`)
    .join('')
  return `<div class="sf-info-grid">${cards}</div>`
}

export function paymentMethodsPreview(_props: Props, data: StorefrontPayload): string {
  if (!data.payment_methods.length) {
    return '<p class="sf-empty">Formas de pagamento não cadastradas.</p>'
  }
  const badges = data.payment_methods
    .map((method) => `<span class="sf-badge sf-badge--muted">${escapeHtml(method.name)}</span>`)
    .join('')
  return `<div style="display:flex;flex-wrap:wrap;gap:10px">${badges}</div>`
}

export function announcementPreview(props: Props): string {
  return `<div class="sf-announcement"><span>${escapeHtml(
    str(props, 'message', 'Mensagem da faixa'),
  )}</span>${bool(props, 'dismissible', false) ? `<button type="button" class="sf-announcement__close">${materialIconMarkup('close', 14)}</button>` : ''}</div>`
}

const SOCIAL_NETWORKS: Array<[string, string]> = [
  ['instagram', 'Instagram'],
  ['facebook', 'Facebook'],
  ['tiktok', 'TikTok'],
  ['x', 'X'],
  ['youtube', 'YouTube'],
]

export function socialLinksPreview(props: Props): string {
  // Só as redes que têm URL preenchida — as mesmas que o site vai publicar.
  const links = SOCIAL_NETWORKS.filter(([key]) => str(props, key))
  if (!links.length) {
    return placeholder('Redes sociais', 'Preencha o endereço de ao menos uma rede')
  }
  const chips = links
    .map(([, label]) => `<span class="sf-category-chip">${escapeHtml(label)}</span>`)
    .join('')
  return `<div style="display:flex;flex-wrap:wrap;gap:12px">${chips}</div>`
}

export function whatsappPreview(props: Props): string {
  // NADA de sobrescrever o posicionamento aqui. O botão é `position: fixed` no
  // site, e o canvas é um iframe — dentro dele o `fixed` gruda no viewport do
  // canvas, que é exatamente o comportamento real. Forçar `static` na prévia
  // (como era antes) escondia justamente o efeito que o cliente precisa ver
  // para decidir se quer o botão flutuando ou dentro da página.
  const floating = str(props, 'position', 'floating') !== 'inline'
  const label = str(props, 'label', 'Pedir no WhatsApp')
  return `<span class="sf-floating-button${floating ? '' : ' sf-floating-button--inline'}">${materialIconMarkup('chat', 18)}${escapeHtml(label)}</span>`
}

export function badgePreview(props: Props): string {
  return `<span class="sf-badge sf-badge--${escapeHtml(str(props, 'tone', 'accent'))}">${escapeHtml(
    str(props, 'text', 'Mais vendido'),
  )}</span>`
}

export function ratingPreview(props: Props): string {
  const value = str(props, 'value', '4,8')
  const total = str(props, 'total', '5')
  return `<span class="sf-rating"><span class="sf-rating__star">${materialIconMarkup('star', 14)}</span><span>${escapeHtml(value)} de ${escapeHtml(total)}</span></span>`
}

/**
 * O cabeçalho do site, desenhado no topo do canvas.
 *
 * Não é um bloco: o cabeçalho é do SITE (`MenuSite.header`) e aparece em todas
 * as páginas. Mas montar a home sem vê-lo é montar às cegas — o cliente não
 * enxerga onde a capa começa em relação ao topo real da página, e foi o que
 * fez a capa nascer com respiro errado nos primeiros testes.
 *
 * Marcação igual à do `StorefrontHeader.vue`, para as classes de `blocks.css`
 * pegarem. Aqui é estático e não interativo: o canvas não roda Vue, e um
 * cabeçalho clicável dentro do editor só confundiria.
 */
interface HeaderPreviewMenu {
  items?: Array<{ title?: string; children?: unknown[] }>
}

export function headerPreviewHtml(
  header: Record<string, unknown> | undefined,
  menus: Record<string, HeaderPreviewMenu> | undefined,
  fallbackBrand: string,
): string {
  const config = header ?? {}
  const announcement = (config.announcement ?? {}) as Props
  const location = (config.location ?? {}) as Props
  const search = (config.search ?? {}) as Props
  const actions = (config.actions ?? {}) as Props

  const announceBar = bool(announcement, 'enabled') && (str(announcement, 'text') || str(announcement, 'highlight'))
    ? `<div class="sf-announce"><div class="sf-announce__inner">
         ${str(announcement, 'highlight') ? `<span class="sf-announce__highlight">${escapeHtml(str(announcement, 'highlight'))}</span>` : ''}
         ${str(announcement, 'text') ? `<span>${escapeHtml(str(announcement, 'text'))}</span>` : ''}
         ${str(announcement, 'secondary') ? `<span class="sf-announce__sep">✦</span><span class="sf-announce__secondary">${escapeHtml(str(announcement, 'secondary'))}</span>` : ''}
       </div></div>`
    : ''

  const locationBox = bool(location, 'enabled') && str(location, 'value')
    ? `<div class="sf-location"><span class="sf-location__text">
         <small>${escapeHtml(str(location, 'label', 'Entregar em'))}</small>
         <strong>${escapeHtml(str(location, 'value'))}</strong>
       </span></div>`
    : ''

  const searchBox = bool(search, 'enabled')
    ? `<div class="sf-search sf-site-header__search"><span class="sf-search__icon">${materialIconMarkup('search', 15)}</span>
         <span style="color:var(--sf-muted-text);font-size:13px">${escapeHtml(
           str(search, 'placeholder', 'Buscar produtos e categorias'),
         )}</span></div>`
    : ''

  // Os três modos do cabeçalho (só ícone, ícone + texto, só texto) desenhados
  // com as MESMAS classes do site — é o que faz a escolha aparecer no canvas.
  const display = str(actions, 'display', 'icon')
  const withIcon = display !== 'text'
  const withLabel = display !== 'icon'
  const actionButton = (variant: 'cart' | 'profile', icon: 'shopping_cart' | 'person', label: string) =>
    `<span class="sf-actions__btn sf-actions__btn--${variant}">${
      withIcon ? materialIconMarkup(icon, 16) : ''
    }${withLabel ? `<span class="sf-actions__label">${escapeHtml(label)}</span>` : ''}</span>`

  const actionButtons = `<div class="sf-actions sf-actions--${escapeHtml(display)}">
    ${bool(actions, 'cart') ? actionButton('cart', 'shopping_cart', str(actions, 'cart_label', 'Carrinho')) : ''}
    ${bool(actions, 'profile') ? actionButton('profile', 'person', str(actions, 'profile_label', 'Entrar')) : ''}
  </div>`

  const navGroup = (handle: string, extraClass = '') => {
    const items = menus?.[handle]?.items ?? []
    if (!items.length) return ''
    const links = items
      .slice(0, 8)
      .map((item) => `<li class="sf-nav__item"><span class="sf-nav__link">${escapeHtml(item.title ?? '')}</span></li>`)
      .join('')
    return `<ul class="sf-nav__group${extraClass}">${links}</ul>`
  }

  const left = navGroup(str(config, 'nav_menu'))
  const right = navGroup(str(config, 'secondary_menu'), ' sf-nav__group--end')
  const nav = left || right ? `<nav class="sf-nav"><div class="sf-nav__inner">${left}${right}</div></nav>` : ''

  return `<header class="sf-site-header"><div class="sf-site-header__card">
    ${announceBar}
    <div class="sf-site-header__main">
      <span class="sf-site-header__brand">${escapeHtml(str(config, 'brand_name', fallbackBrand))}</span>
      ${locationBox}${searchBox}${actionButtons}
    </div>
    ${nav}
  </div></header>`
}
