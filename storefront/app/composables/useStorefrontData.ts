/**
 * Acesso dos blocos aos dados reais do restaurante.
 *
 * Todo bloco dinâmico (vitrine, categorias, horários) chama isto em vez de
 * receber produtos por prop ou buscar na API por conta própria. O payload é
 * um só, veio numa requisição e é lido por injeção — um `sf-product-grid`
 * aninhado em quatro seções não deve obrigar cada nível a repassar a lista, e
 * muito menos disparar uma segunda chamada.
 *
 * Devolve estrutura vazia quando não há payload (bloco renderizado fora do
 * renderer, como no canvas do editor). Vazio é melhor que exceção: um erro
 * derrubaria a página inteira por causa de um bloco.
 */
import type { StorefrontPayload } from '~~/types/storefront'
import { STOREFRONT_KEY } from '~~/lib/builder/registry/injection'
import { EMPTY_STOREFRONT } from '~~/lib/storefront/resolve'

export function useStorefrontData() {
  const injected = inject(STOREFRONT_KEY, null)
  return computed<StorefrontPayload>(() => injected?.value ?? EMPTY_STOREFRONT)
}

// Reexportado para o auto-import dos componentes: a formatação de preço mora
// em `lib/storefront/resolve` junto das outras regras que o canvas do editor
// também usa, para não existirem duas versões do mesmo "R$".
export { formatPrice } from '~~/lib/storefront/resolve'
