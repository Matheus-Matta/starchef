/**
 * O que cada bloco MOSTRA, decidido num lugar só.
 *
 * Este módulo existe por causa de um defeito concreto: o canvas do editor
 * desenhava dados inventados ("Produto em destaque", "Primeiro link") enquanto
 * o site publicado mostrava o catálogo de verdade. Pior que a diferença de
 * conteúdo era a de ESTRUTURA — uma vitrine sem produto nenhum aparecia cheia
 * no editor e sumia no site, então o cliente montava a página sobre uma
 * ilusão.
 *
 * A causa não era um valor errado em algum lugar: era haver DUAS
 * implementações da mesma regra — a do componente Vue e a da prévia do canvas.
 * Duas implementações divergem sempre; é só questão de qual correção chega
 * primeiro a uma delas. Aqui a regra é escrita uma vez e as duas telas a
 * chamam, então "editor diferente do site" deixa de ser possível por
 * construção.
 *
 * Nada aqui depende de Vue nem do GrapesJS: são funções puras sobre o payload
 * público, para poderem ser chamadas do renderer, do canvas e de um teste.
 */
import type {
  StorefrontCategory,
  StorefrontMenuEntry,
  StorefrontPayload,
  StorefrontProduct,
} from '~~/types/storefront'

/**
 * O payload de um site que ainda não respondeu.
 *
 * Vazio é um estado legítimo, não um erro: o bloco pode estar sendo desenhado
 * fora do renderer (canvas do editor) ou antes de a chamada pública voltar.
 * Devolver esta estrutura em vez de lançar mantém a página de pé — um bloco
 * sem dados mostra o próprio vazio ("nenhum produto"), que é exatamente o que
 * o site publicado mostraria.
 */
export const EMPTY_STOREFRONT: StorefrontPayload = {
  restaurant: {
    id: '',
    name: '',
    logo: '',
    phone: '',
    email: '',
    address: { street: '', district: '', city: '', state: '', zip_code: '' },
  },
  site: { id: '', slug: '', name: '', theme: {}, seo: {}, header: {}, is_active: true },
  page: null,
  pages: [],
  categories: [],
  products: [],
  addons: [],
  promotions: [],
  opening_hours: [],
  delivery: { enabled: false, zones: [] },
  payment_methods: [],
  branches: [],
  menus: {},
}

/** `"49.90"` → `"R$ 49,90"`. Nunca lança: preço ausente vira string vazia. */
export function formatPrice(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return ''
  const amount = Number(value)
  if (!Number.isFinite(amount)) return ''
  return amount.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

type Props = Record<string, unknown>

export function propString(props: Props | undefined, key: string, fallback = ''): string {
  const value = props?.[key]
  return typeof value === 'string' && value.trim() ? value : fallback
}

export function propBool(props: Props | undefined, key: string, fallback: boolean): boolean {
  const value = props?.[key]
  return typeof value === 'boolean' ? value : fallback
}

export function propInt(props: Props | undefined, key: string, fallback: number): number {
  const value = Number(props?.[key])
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback
}

/**
 * Colunas por dispositivo, aceitando as duas formas em que elas existem.
 *
 * O backend escreve aninhado (`columns: {desktop: 4}`) na home padrão; os
 * traits do editor escrevem plano (`columns_desktop: 4`), porque o painel do
 * GrapesJS não tem campo aninhado. O plano vence quando existe — é o valor que
 * o cliente acabou de escolher.
 */
export function columnCount(props: Props | undefined, device: string, fallback: number): number {
  const flat = Number(props?.[`columns_${device}`])
  if (Number.isFinite(flat) && flat > 0) return Math.floor(flat)
  const nested = (props?.columns ?? {}) as Record<string, unknown>
  const value = Number(nested[device])
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback
}

// ── Vitrines ─────────────────────────────────────────────────────────────────

export interface ShowcaseFilter {
  categoryId?: string
  sort?: string
}

/**
 * Produtos do MENU vinculado, na ordem em que ele os define.
 *
 * `null` quando não há menu, ou quando o handle salvo não existe mais no site
 * (menu apagado depois de vinculado) — nesse caso o bloco volta ao
 * comportamento por filtro, em vez de mostrar uma vitrine vazia.
 *
 * Item do tipo `product` resolve para o produto correspondente; item do tipo
 * `category` expande para todos os produtos daquela categoria. Um id que não
 * existe mais entre os produtos (produto apagado depois de entrar no menu) é
 * ignorado, não quebra a vitrine.
 */
export function productsFromMenu(
  payload: StorefrontPayload,
  handle: string,
): StorefrontProduct[] | null {
  if (!handle) return null
  const menu = payload.menus?.[handle]
  if (!menu) return null

  const byId = new Map(payload.products.map((product) => [product.id, product]))
  const seen = new Set<string>()
  const resolved: StorefrontProduct[] = []

  const add = (product: StorefrontProduct | undefined) => {
    if (product && !seen.has(product.id)) {
      seen.add(product.id)
      resolved.push(product)
    }
  }

  for (const entry of menu.items) {
    if (entry.type === 'product' && entry.product_id) {
      add(byId.get(entry.product_id))
    } else if (entry.type === 'category' && entry.category_id) {
      for (const product of payload.products) {
        if (product.category_id === entry.category_id) add(product)
      }
    }
  }
  return resolved
}

/** Ordena e corta a lista conforme a configuração do bloco. */
function applyFilter(
  products: StorefrontProduct[],
  options: { categoryId?: string; limit: number; sort: string; onlyPromotions: boolean },
): StorefrontProduct[] {
  let rows = products

  if (options.onlyPromotions) {
    rows = rows.filter((product) => Boolean(product.promotional_price))
  }
  if (options.categoryId) {
    rows = rows.filter((product) => product.category_id === options.categoryId)
  }

  if (options.sort === 'price_asc' || options.sort === 'price_desc') {
    const direction = options.sort === 'price_asc' ? 1 : -1
    rows = [...rows].sort(
      (a, b) => direction * (Number(a.current_price ?? 0) - Number(b.current_price ?? 0)),
    )
  } else if (options.sort === 'name') {
    rows = [...rows].sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'))
  }

  return options.limit > 0 ? rows.slice(0, options.limit) : rows
}

/**
 * Os produtos de uma vitrine — a regra completa, do jeito que o site aplica.
 *
 * `live` é a escolha que o VISITANTE acabou de fazer na barra de filtros; ela
 * vence a configuração salva no bloco. No canvas do editor não existe
 * visitante, então ela chega vazia e vale só o que está configurado.
 */
export function resolveShowcaseProducts(
  payload: StorefrontPayload,
  props: Props | undefined,
  nodeType: string,
  live: ShowcaseFilter = {},
): StorefrontProduct[] {
  const limit = propInt(props, 'limit', 0)

  // O menu, quando vinculado, É a seleção: substitui categoria, ordenação,
  // "só promoções" e o filtro do visitante. A curadoria do restaurante vence a
  // configuração solta.
  const curated = productsFromMenu(payload, propString(props, 'menu'))
  if (curated) return limit > 0 ? curated.slice(0, limit) : curated

  return applyFilter(payload.products, {
    categoryId: live.categoryId || propString(props, 'category_id'),
    limit,
    sort: live.sort && live.sort !== 'default' ? live.sort : propString(props, 'sort', 'default'),
    onlyPromotions: nodeType === 'sf-promotions',
  })
}

/** Grade ou carrossel. `sf-product-carousel` nasce em carrossel pelo nome. */
export function showcaseLayout(props: Props | undefined, nodeType: string): 'grid' | 'carousel' {
  const fallback = nodeType === 'sf-product-carousel' ? 'carousel' : 'grid'
  return propString(props, 'layout', fallback) === 'carousel' ? 'carousel' : 'grid'
}

// ── Categorias ───────────────────────────────────────────────────────────────

export interface CategoryLink {
  id: string
  name: string
}

/**
 * As categorias de um bloco: as do menu vinculado ou as do cardápio.
 *
 * Sem menu, só as de raiz — a menos que "incluir subcategorias" esteja ligado.
 * Subcategoria dentro de chip vira uma fileira de botões que ninguém lê.
 */
export function resolveCategories(payload: StorefrontPayload, props: Props | undefined): CategoryLink[] {
  const handle = propString(props, 'menu')
  const menu = handle ? payload.menus?.[handle] : undefined

  const source: CategoryLink[] = menu
    ? menu.items
        .filter((entry) => entry.type === 'category' && entry.category_id)
        .map((entry) => ({ id: entry.category_id as string, name: entry.title }))
    : payload.categories
        .filter((category: StorefrontCategory) => propBool(props, 'show_all', false) || !category.parent_id)
        .map((category) => ({ id: category.id, name: category.name }))

  const limit = propInt(props, 'limit', 0)
  return limit > 0 ? source.slice(0, limit) : source
}

// ── Capa ─────────────────────────────────────────────────────────────────────

export interface HeroSlide {
  id: string
  title: string
  highlight: string
  description: string
  ctaLabel: string
  ctaUrl: string
  image: string
}

/**
 * Os slides da capa: um só (as props do bloco) ou vários (o menu de banners).
 *
 * O destaque em amarelo fica no primeiro slide mesmo no modo carrossel: ele é
 * a identidade da campanha e vem do bloco, não do item do menu.
 */
export function resolveHeroSlides(payload: StorefrontPayload, props: Props | undefined): HeroSlide[] {
  const handle = propString(props, 'menu')
  const items: StorefrontMenuEntry[] = (handle ? payload.menus?.[handle]?.items : undefined) ?? []

  if (items.length) {
    return items.map((entry, index) => ({
      id: entry.id || `slide-${index}`,
      title: entry.title,
      highlight: index === 0 ? propString(props, 'highlight') : '',
      description: entry.subtitle,
      ctaLabel: propString(props, 'cta_label'),
      ctaUrl: entry.url || propString(props, 'cta_url', '#'),
      image: entry.image,
    }))
  }

  return [{
    id: 'single',
    title: propString(props, 'title'),
    highlight: propString(props, 'highlight'),
    description: propString(props, 'description'),
    ctaLabel: propString(props, 'cta_label'),
    ctaUrl: propString(props, 'cta_url', '#'),
    image: propString(props, 'image'),
  }]
}

// ── Rodapé ───────────────────────────────────────────────────────────────────

export interface FooterColumn {
  title: string
  items: StorefrontMenuEntry[]
}

/** As três colunas de links do rodapé — só as que apontam para um menu com itens. */
export function resolveFooterColumns(payload: StorefrontPayload, props: Props | undefined): FooterColumn[] {
  const column = (titleKey: string, menuKey: string): FooterColumn | null => {
    const handle = propString(props, menuKey)
    if (!handle) return null
    const menu = payload.menus?.[handle]
    if (!menu?.items.length) return null
    return { title: propString(props, titleKey, menu.name), items: menu.items }
  }

  return [
    column('link_menu_1_title', 'link_menu_1'),
    column('link_menu_2_title', 'link_menu_2'),
    column('link_menu_3_title', 'link_menu_3'),
  ].filter((entry): entry is FooterColumn => entry !== null)
}
