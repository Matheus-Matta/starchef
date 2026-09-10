/**
 * O que o cliente vê no canvas do editor.
 *
 * Três coisas quebravam aqui, e nenhuma dava erro — só saía errado na tela:
 *
 * 1. **O canvas não recebia o CSS do site.** É um iframe isolado, e nada do
 *    Nuxt chega nele sozinho. O cliente montava a página vendo caixas cinzas e
 *    só descobria a aparência real depois de publicar.
 * 2. **Trait era enfeite.** Desmarcar "mostrar preço" não mudava nada no
 *    canvas, então o cliente não tinha como saber se o clique funcionou.
 * 3. **O conteúdo era inventado.** Produtos, categorias, banners e links de
 *    rodapé eram amostras embutidas, e o site publicava outra coisa — inclusive
 *    com estrutura diferente (uma vitrine vazia aparecia cheia no editor).
 *
 * Os testes aqui prendem as três: a folha do canvas precisa carregar as regras
 * de verdade, cada prévia precisa obedecer à configuração do bloco, e o que
 * ela desenha precisa ser o que o resolvedor — o mesmo que os componentes Vue
 * usam — devolve.
 */
import { describe, expect, it } from 'vitest'
import { canvasStylesheet } from '~~/lib/builder/canvas-styles'
import {
  categoriesPreview,
  deliveryPreview,
  escapeHtml,
  filterBarPreview,
  footerPreview,
  headerPreviewHtml,
  heroPreview,
  openingHoursPreview,
  paymentMethodsPreview,
  productGridPreview,
  restaurantInfoPreview,
  socialLinksPreview,
} from '~~/lib/builder/components/previews'
import { EMPTY_STOREFRONT, resolveShowcaseProducts } from '~~/lib/storefront/resolve'
import { makePayload, makeProduct } from './fixtures'

const DATA = makePayload()
const GRID = 'sf-product-grid'

describe('canvasStylesheet', () => {
  it('leva as regras REAIS dos blocos para dentro do iframe', () => {
    const css = canvasStylesheet({})
    // Se estas sumirem, o canvas volta a desenhar caixas sem estilo.
    expect(css).toContain('.sf-product-card')
    expect(css).toContain('.sf-hero')
    expect(css).toContain('.sf-site-header')
    expect(css).toContain('.sf-category-chip')
  })

  it('leva os tokens padrão, para nada ficar ilegível sem tema', () => {
    const css = canvasStylesheet({})
    expect(css).toContain('--sf-primary')
    expect(css).toContain('--sf-background')
  })

  it('o tema do restaurante vem por último e vence o padrão', () => {
    const css = canvasStylesheet({ '--sf-primary': '#ff0000' })
    const tokensDefault = css.indexOf('--sf-primary:')
    const theme = css.lastIndexOf('--sf-primary:#ff0000')
    expect(theme).toBeGreaterThan(tokensDefault)
  })

  it('não arrasta nenhum `@import` — o iframe não resolveria o caminho', () => {
    // Procura a DIRETIVA (início de linha), não a menção: `blocks.css` cita
    // `@import 'tailwindcss'` no comentário que explica por que ele não está lá.
    const directives = canvasStylesheet({}).match(/^\s*@import/gm) ?? []
    expect(directives).toHaveLength(0)
  })
})

describe('productGridPreview', () => {
  it('desenha os produtos REAIS do restaurante', () => {
    const html = productGridPreview({}, DATA, GRID)
    expect(html).toContain('X-Bacon Crispy')
    expect(html).toContain('Duplo Cheddar')
    // O defeito que originou tudo isto: o canvas mostrava um catálogo que não
    // existia, e o cliente montava a página sobre ele.
    expect(html).not.toContain('Produto em destaque')
  })

  it('mostra exatamente o que o resolvedor devolve — nem mais, nem menos', () => {
    // É esta igualdade que impede editor e site de divergirem de novo: os dois
    // perguntam ao MESMO módulo o que exibir.
    const props = { category_id: 'c2' }
    const expected = resolveShowcaseProducts(DATA, props, GRID)
    const html = productGridPreview(props, DATA, GRID)

    expect(html.match(/<article/g) ?? []).toHaveLength(expected.length)
    for (const product of expected) expect(html).toContain(product.name)
    expect(html).not.toContain('X-Bacon Crispy')
  })

  it('vitrine sem produto fica VAZIA, como no site', () => {
    // Antes, uma seção sem produto nenhum aparecia cheia no editor e sumia ao
    // publicar — a divergência mais cara, porque era estrutural.
    const html = productGridPreview({}, EMPTY_STOREFRONT, GRID)
    expect(html).toContain('sf-empty')
    expect(html).not.toContain('<article')
  })

  it('"Ofertas" mostra só quem tem preço promocional', () => {
    const html = productGridPreview({}, DATA, 'sf-promotions')
    expect(html).toContain('Duplo Cheddar')
    expect(html).not.toContain('X-Bacon Crispy')
  })

  it('o menu vinculado É a seleção, e vence os filtros do bloco', () => {
    const html = productGridPreview({ menu: 'destaques', category_id: 'c1' }, DATA, GRID)
    expect(html).toContain('Duplo Cheddar')
    expect(html).not.toContain('Guaraná lata')
  })

  it('respeita "mostrar preço"', () => {
    expect(productGridPreview({ show_price: true }, DATA, GRID)).toContain('sf-product-card__price')
    expect(productGridPreview({ show_price: false }, DATA, GRID)).not.toContain('sf-product-card__price')
  })

  it('respeita "mostrar imagem" e "mostrar botão"', () => {
    const off = productGridPreview({ show_image: false, show_button: false }, DATA, GRID)
    expect(off).not.toContain('sf-product-card__image')
    expect(off).not.toContain('sf-product-card__add')
  })

  it('usa as colunas escolhidas no trait, e não as do backend', () => {
    // O trait grava plano (`columns_desktop`); a home padrão grava aninhado.
    // O plano é o que o cliente acabou de escolher, então vence.
    const css = productGridPreview({ columns_desktop: 3, columns: { desktop: 6 } }, DATA, GRID)
    expect(css).toContain('--sf-grid-desktop:3')
  })

  it('cai no formato aninhado quando não há trait', () => {
    expect(productGridPreview({ columns: { desktop: 2 } }, DATA, GRID)).toContain('--sf-grid-desktop:2')
  })

  it('o limite do bloco corta a prévia', () => {
    const html = productGridPreview({ limit: 2 }, DATA, GRID)
    expect(html.match(/<article/g) ?? []).toHaveLength(2)
  })

  it('o selo de desconto sai do preço real, não de um número fixo', () => {
    // 44,90 → 34,90 é 22% de desconto.
    expect(productGridPreview({ limit: 3 }, DATA, GRID)).toContain('-22%')
  })

  it('produto sem promoção não ganha selo — `Number(null)` é 0', () => {
    const data = makePayload({ products: [makeProduct({ promotional_price: null })] })
    expect(productGridPreview({}, data, GRID)).not.toContain('sf-badge--sale')
  })

  it('`sf-product-carousel` nasce em carrossel, sem ninguém configurar', () => {
    expect(productGridPreview({}, DATA, 'sf-product-carousel')).toContain('sf-carousel__track')
    expect(productGridPreview({}, DATA, GRID)).not.toContain('sf-carousel__track')
  })
})

describe('heroPreview', () => {
  it('mostra título, destaque e botão vindos das props', () => {
    const html = heroPreview({ title: 'Peça hoje', highlight: 'sem taxa', cta_label: 'Ver cardápio' }, DATA)
    expect(html).toContain('Peça hoje')
    expect(html).toContain('sf-hero__highlight')
    expect(html).toContain('Ver cardápio')
  })

  it('com um menu de banners, mostra o PRIMEIRO banner real', () => {
    const html = heroPreview({ menu: 'banners' }, DATA)
    expect(html).toContain('Combo em dobro')
    expect(html).toContain('Dois por um às terças')
    expect(html).toContain('banner-1.jpg')
  })

  it('um ponto por banner de verdade', () => {
    // Eram três fixos, com qualquer menu vinculado. O cliente contava dois
    // banners no cadastro e via três pontinhos no editor.
    const html = heroPreview({ menu: 'banners' }, DATA)
    expect(html.match(/class="sf-hero__dot["\s]/g) ?? []).toHaveLength(2)
  })

  it('com um banner só, não há carrossel nenhum', () => {
    expect(heroPreview({ menu: 'destaques' }, DATA)).not.toContain('sf-hero__arrow')
    expect(heroPreview({ title: 'Só um' }, DATA)).not.toContain('sf-hero__arrow')
  })

  it('traduz a posição da imagem em classes, como o componente Vue', () => {
    const html = heroPreview({ image_position: 'left-center' }, DATA)
    expect(html).toContain('sf-hero--image-left')
    expect(html).toContain('sf-hero--anchor-center')
  })

  it('leva as medidas dos traits para as variáveis CSS', () => {
    const html = heroPreview({ height: '420px', padding: '72px', image_width: '40%' }, DATA)
    expect(html).toContain('--sf-hero-height:420px')
    expect(html).toContain('--sf-hero-padding:72px')
    expect(html).toContain('--sf-hero-image-width:40%')
  })

  it('sem imagem, mostra onde ela entraria', () => {
    expect(heroPreview({}, DATA)).toContain('sf-canvas-placeholder')
  })
})

describe('categoriesPreview', () => {
  it('desenha as categorias reais, só as de raiz', () => {
    const html = categoriesPreview({}, DATA)
    expect(html).toContain('Burgers')
    expect(html).toContain('Bebidas')
    // Subcategoria dentro de etiqueta vira uma fileira que ninguém lê.
    expect(html).not.toContain('Long necks')
  })

  it('"incluir subcategorias" traz as filhas', () => {
    expect(categoriesPreview({ show_all: true }, DATA)).toContain('Long necks')
  })

  it('troca de formato conforme o trait', () => {
    expect(categoriesPreview({ layout: 'list' }, DATA)).toContain('sf-categories--list')
    expect(categoriesPreview({ layout: 'chips' }, DATA)).not.toContain('sf-categories--list')
  })

  it('sem categoria cadastrada, mostra o vazio do site', () => {
    expect(categoriesPreview({}, EMPTY_STOREFRONT)).toContain('sf-empty')
  })
})

describe('filterBarPreview', () => {
  it('lista as categorias reais nos chips', () => {
    const html = filterBarPreview({}, DATA)
    expect(html).toContain('Todas as categorias')
    expect(html).toContain('Burgers')
  })

  it('some com o que está desligado', () => {
    expect(filterBarPreview({ show_categories: false }, DATA)).not.toContain('sf-filterbar__chips')
    expect(filterBarPreview({ show_sort: false }, DATA)).not.toContain('sf-filterbar__sort')
  })
})

describe('footerPreview', () => {
  it('só desenha a coluna que aponta para um menu', () => {
    expect(footerPreview({}, DATA)).not.toContain('sf-footer__links')
    const html = footerPreview({ link_menu_1: 'institucional', link_menu_1_title: 'Institucional' }, DATA)
    expect(html).toContain('Institucional')
    expect(html).toContain('sf-footer__links')
  })

  it('os links são os do menu, não "Primeiro link"', () => {
    const html = footerPreview({ link_menu_1: 'institucional' }, DATA)
    expect(html).toContain('Política de privacidade')
    expect(html).not.toContain('Primeiro link')
  })

  it('a identificação vem do cadastro', () => {
    const html = footerPreview({}, DATA)
    expect(html).toContain('Burger Palace')
    expect(html).toContain('Rua das Palmeiras, 120')
    expect(html).not.toContain('Nome do restaurante')
  })

  it('um menu apagado depois de vinculado não vira coluna vazia', () => {
    expect(footerPreview({ link_menu_1: 'apagado' }, DATA)).not.toContain('sf-footer__links')
  })
})

describe('blocos de cadastro', () => {
  it('horários vêm da primeira unidade COM horário', () => {
    const html = openingHoursPreview({}, DATA)
    expect(html).toContain('11:00 às 23:00')
    expect(html).toContain('Segunda')
    // A unidade recém-criada e vazia vem primeiro na lista e não pode vencer.
    expect(html).not.toContain('sf-empty')
  })

  it('endereço e contato saem do cadastro do restaurante', () => {
    const html = restaurantInfoPreview({}, DATA)
    expect(html).toContain('Niterói - RJ')
    expect(html).toContain('(21) 99999-0000')
    expect(html).toContain('contato@burgerpalace.com')
  })

  it('zonas de entrega com taxa formatada', () => {
    const html = deliveryPreview({}, DATA)
    expect(html).toContain('Até 3 km')
    expect(html).toContain('35 min')
    expect(html).toMatch(/R\$\s*6,90/)
  })

  it('formas de pagamento são as cadastradas', () => {
    expect(paymentMethodsPreview({}, DATA)).toContain('PIX')
    expect(paymentMethodsPreview({}, EMPTY_STOREFRONT)).toContain('sf-empty')
  })

  it('redes sociais só aparecem quando têm endereço', () => {
    expect(socialLinksPreview({})).toContain('sf-canvas-placeholder')
    const html = socialLinksPreview({ instagram: 'https://instagram.com/burger' })
    expect(html).toContain('Instagram')
    expect(html).not.toContain('Facebook')
  })
})

describe('headerPreviewHtml', () => {
  const menus = { categorias: { items: [{ title: 'Entradas' }, { title: 'Bebidas' }] } }

  it('monta os três níveis a partir da configuração do site', () => {
    const html = headerPreviewHtml(
      {
        brand_name: 'Burger Palace',
        announcement: { enabled: true, highlight: 'Frete grátis', text: 'Peça pelo site' },
        search: { enabled: true, placeholder: 'Buscar' },
        actions: { cart: true, profile: true },
        nav_menu: 'categorias',
      },
      menus,
      'Fallback',
    )

    expect(html).toContain('sf-announce')
    expect(html).toContain('Burger Palace')
    expect(html).toContain('sf-search')
    expect(html).toContain('sf-actions__btn--cart')
    expect(html).toContain('Entradas')
  })

  it('some com o que está desligado', () => {
    const html = headerPreviewHtml(
      { announcement: { enabled: false }, search: { enabled: false }, actions: { cart: false, profile: false } },
      {},
      'Casa',
    )
    expect(html).not.toContain('sf-announce"')
    expect(html).not.toContain('sf-search')
    expect(html).not.toContain('sf-actions__btn')
    // A marca sobra: um cabeçalho sem identificação nenhuma é pior que um
    // com o nome repetido.
    expect(html).toContain('Casa')
  })

  it('sem menu configurado, não desenha a barra de navegação vazia', () => {
    expect(headerPreviewHtml({}, {}, 'Casa')).not.toContain('sf-nav__inner')
  })
})

describe('escapeHtml', () => {
  it('neutraliza o que o cliente digitou no trait', () => {
    // O texto do trait vira HTML do canvas. Sem escapar, um título com
    // `<script>` executaria dentro do editor.
    expect(escapeHtml('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(escapeHtml('aspas " e & comercial')).toBe('aspas &quot; e &amp; comercial')
  })

  it('a prévia da capa escapa o título', () => {
    expect(heroPreview({ title: '<img onerror=alert(1)>' }, DATA)).not.toContain('<img onerror')
  })

  it('escapa também o que veio do cadastro, não só o que veio do trait', () => {
    // Agora que o canvas desenha dados do banco, o nome de um produto é
    // conteúdo de terceiro tanto quanto o texto de um trait.
    const data = makePayload({ products: [makeProduct({ name: '<img onerror=alert(1)>' })] })
    expect(productGridPreview({}, data, GRID)).not.toContain('<img onerror')
  })
})
