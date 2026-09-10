/**
 * Testes do compiler — a tradução entre o editor e o site público.
 *
 * É o ponto onde um erro silencioso custa caro: um bloco que some, um estilo
 * que não vira CSS ou um `javascript:` que passa aparecem no site do cliente,
 * não numa tela interna.
 */
import { describe, expect, it } from 'vitest'
import { compileProject } from '../../lib/builder/compiler/compile-project'
import { safeUrl, sanitizeRichText } from '../../lib/builder/security/sanitize'
import { breakpointFromMedia } from '../../lib/builder/devices/devices'

function project(components: unknown[], styles: unknown[] = []) {
  return {
    pages: [{ frames: [{ component: { type: 'wrapper', components } }] }],
    styles,
  }
}

describe('compileProject', () => {
  it('desembrulha o wrapper e devolve os blocos da página', () => {
    const schema = compileProject(
      project([
        { type: 'sf-section', tagName: 'section', components: [{ type: 'sf-heading', content: 'Oi' }] },
      ]),
    )

    expect(schema.nodes).toHaveLength(1)
    expect(schema.nodes[0]!.type).toBe('sf-section')
    expect(schema.nodes[0]!.children[0]!.type).toBe('sf-heading')
  })

  it('ignora bloco de tipo desconhecido em vez de renderizar um div solto', () => {
    const schema = compileProject(project([{ type: 'sf-checkout-hack' }, { type: 'sf-section' }]))

    expect(schema.nodes.map((node) => node.type)).toEqual(['sf-section'])
  })

  it('descarta propriedade de CSS fora da allowlist', () => {
    const schema = compileProject(
      project([{ type: 'sf-section', style: { padding: '10px', '-moz-binding': 'url(x)' } }]),
    )

    expect(schema.nodes[0]!.styles.desktop).toEqual({ padding: '10px' })
  })

  it('normaliza camelCase de CSS', () => {
    const schema = compileProject(project([{ type: 'sf-section', style: { backgroundColor: '#fff' } }]))

    expect(schema.nodes[0]!.styles.desktop).toEqual({ 'background-color': '#fff' })
  })

  it('separa as regras de estilo por breakpoint e gera as media queries', () => {
    const schema = compileProject(
      project(
        [{ type: 'sf-section', classes: ['hero'] }],
        [
          { selectors: ['.hero'], style: { padding: '64px' } },
          { selectors: ['.hero'], mediaText: '(max-width: 767px)', style: { padding: '24px' } },
        ],
      ),
    )

    const node = schema.nodes[0]!
    expect(node.styles.desktop).toEqual({ padding: '64px' })
    expect(node.styles.mobile).toEqual({ padding: '24px' })
    expect(schema.css).toContain('@media (max-width:767px)')
  })

  it('recusa URL javascript: nos atributos', () => {
    const schema = compileProject(
      project([{ type: 'sf-button', attributes: { href: 'javascript:alert(1)' } }]),
    )

    expect(schema.nodes[0]!.attrs.href).toBeUndefined()
  })

  it('remove handler de evento que porventura chegue no atributo', () => {
    const schema = compileProject(
      project([{ type: 'sf-button', attributes: { onclick: 'steal()', href: '/menu' } }]),
    )

    expect(schema.nodes[0]!.attrs).toEqual({ href: '/menu' })
  })

  it('sanitiza o HTML do texto rico', () => {
    const schema = compileProject(
      project([{ type: 'sf-text', content: '<b>ok</b><script>alert(1)</script>' }]),
    )

    expect(schema.nodes[0]!.content).toContain('<b>ok</b>')
    expect(schema.nodes[0]!.content).not.toContain('alert')
  })

  it('preserva a configuração do bloco sem copiar produto nenhum', () => {
    const schema = compileProject(
      project([
        {
          type: 'sf-product-grid',
          props: { category_id: 'abc', columns: { desktop: 4 }, show_price: true },
        },
      ]),
    )

    expect(schema.nodes[0]!.props).toEqual({
      category_id: 'abc',
      columns: { desktop: 4 },
      show_price: true,
    })
  })

  it('aceita o envelope {schemaVersion, project} e o project cru', () => {
    const raw = project([{ type: 'sf-section' }])
    const wrapped = { schemaVersion: 1, project: raw }

    expect(compileProject(raw).nodes).toHaveLength(1)
    expect(compileProject(wrapped).nodes).toHaveLength(1)
  })

  it('devolve página vazia em vez de estourar com conteúdo malformado', () => {
    expect(compileProject(null).nodes).toEqual([])
    expect(compileProject({ pages: 'nao é lista' }).nodes).toEqual([])
    expect(compileProject({ pages: [{ frames: [{}] }] }).nodes).toEqual([])
  })
})

describe('safeUrl', () => {
  it('aceita http, https, relativo e âncora', () => {
    expect(safeUrl('https://exemplo.com')).toBe('https://exemplo.com')
    expect(safeUrl('/cardapio')).toBe('/cardapio')
    expect(safeUrl('#promo')).toBe('#promo')
    expect(safeUrl('mailto:contato@exemplo.com')).toBe('mailto:contato@exemplo.com')
  })

  it('recusa javascript:, data: e quebra de linha no meio do esquema', () => {
    expect(safeUrl('javascript:alert(1)')).toBe('')
    expect(safeUrl('data:text/html,<script>')).toBe('')
    expect(safeUrl('java\nscript:alert(1)')).toBe('')
    expect(safeUrl('  JAVASCRIPT:alert(1)')).toBe('')
  })
})

describe('sanitizeRichText', () => {
  it('mantém o texto de tags não permitidas e apaga o conteúdo das perigosas', () => {
    expect(sanitizeRichText('<marquee>oi</marquee>')).toBe('oi')
    expect(sanitizeRichText('<script>alert(1)</script>fim')).toBe('fim')
  })

  it('remove handler de evento inline', () => {
    expect(sanitizeRichText('<a href="/x" onclick="mal()">ir</a>')).not.toContain('onclick')
  })
})

describe('breakpointFromMedia', () => {
  it('mapeia as media queries dos três dispositivos', () => {
    expect(breakpointFromMedia(undefined)).toBe('desktop')
    expect(breakpointFromMedia('(max-width: 767px)')).toBe('mobile')
    expect(breakpointFromMedia('(max-width: 1024px)')).toBe('tablet')
    expect(breakpointFromMedia('(min-width: 1600px)')).toBe('desktop')
  })
})
