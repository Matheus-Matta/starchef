/**
 * De qual restaurante é este site? Do SLUG na URL.
 *
 * `/burger/` é o site de um restaurante, `/pizzapalace/` é o de outro, e o
 * mesmo servidor Nuxt atende os dois. O slug de `MenuSite` é único na
 * plataforma inteira (constraint no banco), então ele sozinho identifica o
 * restaurante — não é preciso DNS, arquivo `hosts` nem uma variável de ambiente
 * por loja.
 *
 * Isto substituiu o modo por variável de ambiente, que tinha um defeito
 * incômodo: `STOREFRONT_SITE_SLUG` era lido em tempo de BUILD e ficava
 * congelado na imagem, então trocar de restaurante exigia recompilar. Com o
 * slug na URL, uma imagem serve todas as lojas.
 *
 * Domínio próprio (`pizzaria.com.br` apontando direto para uma loja) fica para
 * depois: o backend já sabe resolver por hostname, mas enquanto não há DNS
 * configurado o endereço por slug é o único que funciona em qualquer ambiente.
 */
export function useStorefrontTenant() {
  const route = useRoute()

  const slug = computed(() => String(route.params.site ?? '').trim())
  /** Prefixo de todo link interno deste site: `/burger` (ou vazio fora dele). */
  const base = computed(() => (slug.value ? `/${slug.value}` : ''))

  return { slug, base }
}

/**
 * Prefixa um caminho interno com o endereço do site.
 *
 * Sem isso, um link para `/promocoes` sairia de `/burger/` e cairia na raiz do
 * servidor — ou, pior, no site de outro restaurante se alguém registrasse esse
 * slug. Tudo o que já é absoluto (`https://`, `mailto:`, `tel:`) ou é uma
 * âncora (`#cardapio`) passa intacto: prefixar aquilo quebraria o link.
 */
export function siteHref(base: string, path?: string | null): string {
  const raw = String(path ?? '').trim()
  if (!raw) return base || '/'
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw) || raw.startsWith('//') || raw.startsWith('#')) return raw
  if (!raw.startsWith('/')) return raw
  return `${base}${raw}` || '/'
}

/** Versão reativa do `siteHref`, já amarrada ao site da rota atual. */
export function useSiteLink() {
  const { base } = useStorefrontTenant()
  return (path?: string | null) => siteHref(base.value, path)
}
