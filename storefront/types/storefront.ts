/**
 * Tipos do payload público e do schema de renderização.
 *
 * Espelham o que `GET /api/v1/public/storefront/<slug>/` devolve (ver
 * `backend/apps/storefront/services/public_payload.py`). Se o backend mudar o
 * contrato, é aqui que a divergência tem de aparecer primeiro.
 */

export interface StorefrontTheme {
  mode?: 'light' | 'dark'
  primaryColor?: string
  secondaryColor?: string
  accentColor?: string
  backgroundColor?: string
  surfaceColor?: string
  textColor?: string
  mutedTextColor?: string
  borderColor?: string
  /** Selo de desconto. Vermelho por convenção, mas do tema como qualquer outra. */
  saleColor?: string
  /** Texto sobre as cores de ação — branco sobre o primário, escuro sobre o destaque. */
  onPrimaryColor?: string
  onAccentColor?: string
  whatsappColor?: string
  /** O cabeçalho tem fundo próprio, mas sai da mesma paleta. */
  headerBackgroundColor?: string
  announcementBackgroundColor?: string
  announcementTextColor?: string
  fontFamily?: string
  headingFontFamily?: string
  borderRadius?: string
  containerWidth?: string
  spacing?: string
  buttonStyle?: string
  logoUrl?: string
  faviconUrl?: string
}

/** Configuração do cabeçalho — vem do SITE, nunca de um bloco da página. */
export interface StorefrontHeaderConfig {
  sticky?: boolean
  brand_name?: string
  logo_url?: string
  announcement?: {
    enabled?: boolean
    text?: string
    /** Trecho em destaque (amarelo) dentro da faixa. */
    highlight?: string
    secondary?: string
    url?: string
  }
  location?: { enabled?: boolean; label?: string; value?: string }
  search?: { enabled?: boolean; placeholder?: string }
  actions?: {
    cart?: boolean
    profile?: boolean
    /** `icon` só o círculo, `icon_text` ícone + rótulo, `text` só a palavra. */
    display?: 'icon' | 'icon_text' | 'text'
    cart_label?: string
    profile_label?: string
  }
  /** Handles de `menu.Menu` — o payload entrega os menus resolvidos em `menus`. */
  nav_menu?: string
  secondary_menu?: string
}

/** Uma entrada de menu já resolvida pelo backend (ver `menu_resolver.py`). */
export interface StorefrontMenuEntry {
  id: string
  type: 'product' | 'category' | 'image' | 'custom'
  title: string
  subtitle: string
  image: string
  url: string
  opens_in_new_tab: boolean
  product_id: string | null
  category_id: string | null
  price: string | null
  compare_at_price: string | null
  children: StorefrontMenuEntry[]
}

export interface StorefrontMenu {
  id: string
  slug: string
  name: string
  type: string
  source: string
  items: StorefrontMenuEntry[]
}

export interface StorefrontSeo {
  title?: string
  description?: string
  keywords?: string
  og_image?: string
  canonical_url?: string
  index?: boolean
}

export interface StorefrontCategory {
  id: string
  name: string
  parent_id: string | null
  display_order: number
  logo_url: string
}

export interface StorefrontVariation {
  id: string
  name: string
  price_delta: string | null
  logo_p: string
}

export interface StorefrontProductImage {
  id: string
  url: string
  is_primary: boolean
  position: number
}

export interface StorefrontProduct {
  id: string
  name: string
  description: string
  category_id: string | null
  image: string
  logo_p: string
  photo_list: StorefrontProductImage[]
  price: string | null
  promotional_price: string | null
  current_price: string | null
  pricing_unit: string
  is_weighed: boolean
  product_type: string
  preparation_minutes: number
  allows_addons: boolean
  allows_notes: boolean
  requires_variation: boolean
  available_for_delivery: boolean
  available_for_counter: boolean
  variations: StorefrontVariation[]
  addon_ids: string[]
}

export interface StorefrontAddon {
  id: string
  name: string
  price: string | null
}

export interface StorefrontOpeningHours {
  branch_id: string
  branch_name: string
  hours: Record<string, unknown>
}

export interface StorefrontDeliveryZone {
  id: string
  name: string
  min_radius_km: string
  max_radius_km: string
  delivery_fee: string | null
  estimated_minutes: number
}

export interface StorefrontBranch {
  id: string
  name: string
  phone: string
  address: string
  district: string
  city: string
  state: string
  zip_code: string
}

export interface StorefrontPaymentMethod {
  id: string
  name: string
  method_type: string
}

/** O conteúdo do editor: project data do GrapesJS, já sanitizado pelo backend. */
export interface BuilderProject {
  pages?: Array<{
    name?: string
    frames?: Array<{ component?: BuilderComponent }>
  }>
  styles?: BuilderStyleRule[]
  assets?: unknown[]
  meta?: Record<string, unknown>
}

export interface BuilderComponent {
  type?: string
  tagName?: string
  name?: string
  classes?: string[]
  attributes?: Record<string, string | number | boolean | null>
  style?: Record<string, string | number>
  content?: string
  props?: Record<string, unknown>
  components?: Array<BuilderComponent | string>
}

export interface BuilderStyleRule {
  selectors?: string[]
  selectorsAdd?: string
  mediaText?: string
  state?: string
  style?: Record<string, string | number>
}

export interface StorefrontPage {
  id: string
  title: string
  slug: string
  is_home: boolean
  seo: StorefrontSeo
  published_at: string | null
  data: BuilderProject
}

export interface StorefrontPageLink {
  title: string
  slug: string
  is_home: boolean
}

export interface StorefrontPayload {
  restaurant: {
    id: string
    name: string
    logo: string
    phone: string
    email: string
    address: {
      street: string
      district: string
      city: string
      state: string
      zip_code: string
    }
  }
  site: {
    id: string
    slug: string
    name: string
    theme: StorefrontTheme
    seo: StorefrontSeo
    header: StorefrontHeaderConfig
    is_active: boolean
  }
  page: StorefrontPage | null
  pages: StorefrontPageLink[]
  categories: StorefrontCategory[]
  products: StorefrontProduct[]
  addons: StorefrontAddon[]
  promotions: StorefrontProduct[]
  opening_hours: StorefrontOpeningHours[]
  delivery: { enabled: boolean; zones: StorefrontDeliveryZone[] }
  payment_methods: StorefrontPaymentMethod[]
  branches: StorefrontBranch[]
  /** Menus resolvidos, indexados por handle. */
  menus: Record<string, StorefrontMenu>
  preview?: boolean
}
