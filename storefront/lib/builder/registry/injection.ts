/**
 * Chaves de injeção do renderer.
 *
 * Ficam num arquivo próprio para não criar um ciclo de import: o renderer
 * fornece os valores e os blocos os consomem, e se as chaves morassem em
 * qualquer um dos dois lados eles passariam a se importar mutuamente.
 */
import type { ComputedRef, InjectionKey } from 'vue'
import type { StorefrontPayload } from '~~/types/storefront'
import type { StorefrontFilterState } from '~/composables/useStorefrontFilter'

export const STOREFRONT_KEY: InjectionKey<ComputedRef<StorefrontPayload>> = Symbol('storefront')

/** Filtro/ordenação partilhados entre a barra de filtros e a vitrine. */
export const STOREFRONT_FILTER_KEY: InjectionKey<StorefrontFilterState> = Symbol('storefront-filter')
