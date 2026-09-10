/**
 * Regra de desconto do cartão de produto.
 *
 * Existe por causa de um bug real: `Number(null)` é 0, então todo produto SEM
 * promoção era exibido com selo "-100%" — como se estivesse sendo dado de
 * graça. A ausência de promoção precisa ser testada antes da conversão.
 */
import { describe, expect, it } from 'vitest'

function discountPercent(product: { price: string | null; promotional_price: string | null }): number {
  if (product.promotional_price === null || product.promotional_price === undefined || product.promotional_price === '') {
    return 0
  }
  const full = Number(product.price)
  const promo = Number(product.promotional_price)
  if (!Number.isFinite(full) || !Number.isFinite(promo) || full <= 0 || promo >= full) return 0
  return Math.round(((full - promo) / full) * 100)
}

describe('discountPercent', () => {
  it('não inventa desconto para produto sem promoção', () => {
    expect(discountPercent({ price: '49.90', promotional_price: null })).toBe(0)
    expect(discountPercent({ price: '49.90', promotional_price: '' })).toBe(0)
  })

  it('calcula o percentual quando há promoção de verdade', () => {
    expect(discountPercent({ price: '52.00', promotional_price: '39.90' })).toBe(23)
    expect(discountPercent({ price: '100.00', promotional_price: '75.00' })).toBe(25)
  })

  it('ignora promoção que não é desconto', () => {
    expect(discountPercent({ price: '10.00', promotional_price: '10.00' })).toBe(0)
    expect(discountPercent({ price: '10.00', promotional_price: '12.00' })).toBe(0)
    expect(discountPercent({ price: null, promotional_price: '5.00' })).toBe(0)
  })
})
