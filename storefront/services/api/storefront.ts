/**
 * Leitura do cardápio público.
 *
 * Uma requisição por página: o backend devolve restaurante, tema, blocos,
 * categorias, produtos, horários, entrega e formas de pagamento de uma vez
 * (ver `apps/storefront/services/public_payload.py`). No 4G do cliente, seis
 * idas ao servidor seriam a diferença entre o pedido acontecer e não acontecer.
 */
import type { StorefrontPayload } from '~~/types/storefront'
import { publicApi } from './client'

export interface FetchStorefrontOptions {
  /** Slug do site — o primeiro segmento da URL (`/burger/`). */
  slug: string
  /** Página interna; vazio abre a home. */
  page?: string
}

/**
 * Busca o cardápio de um site pelo slug.
 *
 * O slug de `MenuSite` é único na plataforma inteira, então ele sozinho já diz
 * de qual restaurante é a página — o mesmo processo Nuxt atende todas as lojas
 * sem precisar de DNS por cliente. A resolução por domínio próprio existe no
 * backend (`/storefront/by-host/`) e volta a ser usada quando os domínios
 * entrarem; por ora, todo endereço passa pelo slug.
 */
export function fetchStorefront(options: FetchStorefrontOptions): Promise<StorefrontPayload> {
  return publicApi<StorefrontPayload>(`/storefront/${options.slug}/`, {
    query: options.page ? { page: options.page } : undefined,
  })
}
