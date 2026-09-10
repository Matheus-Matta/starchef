/**
 * Prefixo de site nos links internos.
 *
 * Um único servidor Nuxt atende todas as lojas, e cada uma vive sob `/{slug}/`.
 * Um link para `/promocoes` sem o prefixo sai de `/burger/` e cai na raiz do
 * servidor — ou, se alguém registrar esse slug, no site de outro restaurante.
 * É o pior tipo de bug de multi-loja: silencioso, e leva o cliente de um
 * restaurante para o cardápio de outro.
 *
 * A outra metade da regra é igualmente importante: âncoras, `tel:`, `mailto:` e
 * URLs absolutas NÃO podem ser prefixadas. Prefixar `#cardapio` viraria
 * `/burger#cardapio` (recarrega a página em vez de rolar) e prefixar
 * `https://wa.me/...` quebraria o botão de WhatsApp.
 */
import { describe, expect, it } from 'vitest'
import { siteHref } from '~/composables/useStorefrontTenant'

const BASE = '/burger'

describe('siteHref', () => {
  it('prefixa caminho interno com o endereço do site', () => {
    expect(siteHref(BASE, '/promocoes')).toBe('/burger/promocoes')
    expect(siteHref(BASE, '/categoria/abc-123')).toBe('/burger/categoria/abc-123')
  })

  it('a raiz do site é o próprio prefixo', () => {
    expect(siteHref(BASE, '/')).toBe('/burger/')
    expect(siteHref(BASE, '')).toBe('/burger')
    expect(siteHref(BASE, null)).toBe('/burger')
    expect(siteHref(BASE, undefined)).toBe('/burger')
  })

  it('não toca em âncora — prefixar recarregaria a página em vez de rolar', () => {
    expect(siteHref(BASE, '#cardapio')).toBe('#cardapio')
    expect(siteHref(BASE, '#categoria-abc')).toBe('#categoria-abc')
  })

  it('não toca em URL absoluta nem em esquema não-http', () => {
    expect(siteHref(BASE, 'https://wa.me/5521999')).toBe('https://wa.me/5521999')
    expect(siteHref(BASE, 'http://exemplo.com')).toBe('http://exemplo.com')
    expect(siteHref(BASE, 'mailto:contato@casa.com')).toBe('mailto:contato@casa.com')
    expect(siteHref(BASE, 'tel:+5521999')).toBe('tel:+5521999')
    // Protocol-relative: `//cdn.x/y` é externo, não um caminho interno.
    expect(siteHref(BASE, '//cdn.exemplo.com/foto.jpg')).toBe('//cdn.exemplo.com/foto.jpg')
  })

  it('caminho relativo resolve sozinho e passa intacto', () => {
    expect(siteHref(BASE, 'promocoes')).toBe('promocoes')
  })

  it('sem site (canvas do editor) devolve caminho utilizável', () => {
    // O editor renderiza os mesmos blocos fora de uma rota de site. Nada de
    // `undefined/promocoes` no href.
    expect(siteHref('', '/promocoes')).toBe('/promocoes')
    expect(siteHref('', '')).toBe('/')
    expect(siteHref('', '#cardapio')).toBe('#cardapio')
  })

  it('ignora espaço em volta, que vem de campo digitado no editor', () => {
    expect(siteHref(BASE, '  /promocoes  ')).toBe('/burger/promocoes')
  })

  it('cada loja recebe o próprio prefixo', () => {
    expect(siteHref('/pizzapalace', '/promocoes')).toBe('/pizzapalace/promocoes')
    expect(siteHref('/burger', '/promocoes')).not.toBe(siteHref('/pizzapalace', '/promocoes'))
  })
})
