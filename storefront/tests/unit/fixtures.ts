/**
 * Um restaurante de mentira para os testes — mas com a FORMA do payload real.
 *
 * A fixture existe para que os testes possam exercitar as prévias do canvas
 * com dados, agora que elas desenham o catálogo de verdade em vez de exemplos
 * embutidos. Os nomes são propositalmente reconhecíveis ("X-Bacon", "Combo em
 * dobro"): quando um teste falha, a mensagem já diz de onde o valor veio.
 */
import type {
  StorefrontCategory,
  StorefrontMenu,
  StorefrontMenuEntry,
  StorefrontPayload,
  StorefrontProduct,
} from '~~/types/storefront'

export function makeProduct(overrides: Partial<StorefrontProduct> = {}): StorefrontProduct {
  return {
    id: 'p1',
    name: 'X-Bacon Crispy',
    description: 'Pão brioche, dois hambúrgueres e bacon',
    category_id: 'c1',
    image: 'https://cdn.example/x-bacon.jpg',
    logo_p: '',
    photo_list: [],
    price: '39.90',
    promotional_price: null,
    current_price: '39.90',
    pricing_unit: 'un',
    is_weighed: false,
    product_type: 'prepared',
    preparation_minutes: 20,
    allows_addons: true,
    allows_notes: true,
    requires_variation: false,
    available_for_delivery: true,
    available_for_counter: true,
    variations: [],
    addon_ids: [],
    ...overrides,
  }
}

export function makeCategory(overrides: Partial<StorefrontCategory> = {}): StorefrontCategory {
  return { id: 'c1', name: 'Burgers', parent_id: null, display_order: 0, logo_url: '', ...overrides }
}

export function makeMenuEntry(overrides: Partial<StorefrontMenuEntry> = {}): StorefrontMenuEntry {
  return {
    id: 'e1',
    type: 'custom',
    title: 'Sobre nós',
    subtitle: '',
    image: '',
    url: '/sobre',
    opens_in_new_tab: false,
    product_id: null,
    category_id: null,
    price: null,
    compare_at_price: null,
    children: [],
    ...overrides,
  }
}

export function makeMenu(overrides: Partial<StorefrontMenu> = {}): StorefrontMenu {
  return {
    id: 'm1',
    slug: 'institucional',
    name: 'Institucional',
    type: 'custom',
    source: 'manual',
    items: [makeMenuEntry()],
    ...overrides,
  }
}

/** O payload de um restaurante com catálogo, menus, horários e pagamentos. */
export function makePayload(overrides: Partial<StorefrontPayload> = {}): StorefrontPayload {
  return {
    restaurant: {
      id: 'r1',
      name: 'Burger Palace',
      logo: '',
      phone: '(21) 99999-0000',
      email: 'contato@burgerpalace.com',
      address: {
        street: 'Rua das Palmeiras, 120',
        district: 'Centro',
        city: 'Niterói',
        state: 'RJ',
        zip_code: '24020-000',
      },
    },
    site: {
      id: 's1',
      slug: 'burger',
      name: 'Burger Palace',
      theme: {},
      seo: {},
      header: {},
      is_active: true,
    },
    page: null,
    pages: [],
    categories: [
      makeCategory(),
      makeCategory({ id: 'c2', name: 'Bebidas', display_order: 1 }),
      makeCategory({ id: 'c3', name: 'Long necks', parent_id: 'c2', display_order: 2 }),
    ],
    products: [
      makeProduct(),
      makeProduct({
        id: 'p2',
        name: 'Duplo Cheddar',
        price: '44.90',
        promotional_price: '34.90',
        current_price: '34.90',
      }),
      makeProduct({ id: 'p3', name: 'Guaraná lata', category_id: 'c2', price: '7.00', current_price: '7.00' }),
    ],
    addons: [],
    promotions: [],
    opening_hours: [
      { branch_id: 'b0', branch_name: 'Unidade recém-criada', hours: {} },
      {
        branch_id: 'b1',
        branch_name: 'Centro',
        hours: { monday: '11:00 às 23:00', tuesday: { open: '11:00', close: '23:00' } },
      },
    ],
    delivery: {
      enabled: true,
      zones: [
        {
          id: 'z1',
          name: 'Até 3 km',
          min_radius_km: '0',
          max_radius_km: '3',
          delivery_fee: '6.90',
          estimated_minutes: 35,
        },
      ],
    },
    payment_methods: [
      { id: 'pm1', name: 'PIX', method_type: 'pix' },
      { id: 'pm2', name: 'Crédito', method_type: 'credit' },
    ],
    branches: [],
    menus: {
      institucional: makeMenu({
        items: [
          makeMenuEntry({ id: 'e1', title: 'Sobre nós', url: '/sobre' }),
          makeMenuEntry({ id: 'e2', title: 'Política de privacidade', url: '/privacidade' }),
        ],
      }),
      destaques: makeMenu({
        id: 'm2',
        slug: 'destaques',
        name: 'Destaques',
        items: [makeMenuEntry({ id: 'e3', type: 'product', title: 'Duplo Cheddar', product_id: 'p2' })],
      }),
      banners: makeMenu({
        id: 'm3',
        slug: 'banners',
        name: 'Banners',
        items: [
          makeMenuEntry({
            id: 'e4',
            type: 'image',
            title: 'Combo em dobro',
            subtitle: 'Dois por um às terças',
            image: 'https://cdn.example/banner-1.jpg',
          }),
          makeMenuEntry({
            id: 'e5',
            type: 'image',
            title: 'Frete grátis',
            image: 'https://cdn.example/banner-2.jpg',
          }),
        ],
      }),
    },
    ...overrides,
  }
}
