/**
 * API privada do editor.
 *
 * Salvar NUNCA publica: `PATCH` grava em `draft_data`, e só `POST .../publish/`
 * move o rascunho para o que o público vê. É a mesma invariante do backend, e
 * o editor não deve ser o lugar onde ela se perde.
 */
import type { BuilderProject, StorefrontHeaderConfig, StorefrontPayload, StorefrontTheme } from '~~/types/storefront'
import { appApi, privateApi } from './client'

export interface BuilderPage {
  id: string
  site: string
  title: string
  slug: string
  is_home: boolean
  display_order?: number
  status: 'draft' | 'published' | 'archived'
  draft_data: BuilderProject
  published_data: BuilderProject
  has_unpublished_changes: boolean
  published_at: string | null
  seo: Record<string, unknown>
}

export interface BuilderSectionPreset {
  key: string
  label: string
  component: Record<string, unknown>
}

export interface BuilderSchemaContract {
  components: string[]
  data_components: string[]
  tags: string[]
  style_properties: string[]
  attributes: string[]
  attribute_prefixes: string[]
  rich_text_tags: string[]
  url_schemes: string[]
  /** Seções prontas (as mesmas que montam a home padrão). */
  sections: BuilderSectionPreset[]
  limits: { max_project_bytes: number; max_nodes: number; max_depth: number }
}

export interface ThemePreset {
  key: string
  name: string
  description: string
  tokens: StorefrontTheme
}

export interface BuilderSite {
  id: string
  restaurant: string
  restaurant_name: string
  name: string
  slug: string
  is_active: boolean
  catalog: string | null
  theme: StorefrontTheme
  theme_preset: string
  seo: Record<string, unknown>
  /** Cabeçalho global — vive no site, não em um bloco apagável da página. */
  header: StorefrontHeaderConfig
  primary_domain: string
  pages_count: number
  published_at: string | null
}

export function fetchPage(pageId: string): Promise<BuilderPage> {
  return privateApi<BuilderPage>(`/pages/${pageId}/`)
}

export function fetchSite(siteId: string): Promise<BuilderSite> {
  return privateApi<BuilderSite>(`/sites/${siteId}/`)
}

/**
 * Salva as configurações do site (tema, SEO, identidade, catálogo).
 *
 * PATCH parcial: manda só o que mudou. `theme` e `seo` são fundidos com o que
 * já está salvo no servidor (`_merge_with_instance`), então editar uma cor não
 * apaga os outros tokens.
 */
export function updateSite(siteId: string, payload: Partial<BuilderSite>): Promise<BuilderSite> {
  return privateApi<BuilderSite>(`/sites/${siteId}/`, { method: 'PATCH', body: payload })
}

/** Salva os metadados da página (título, endereço, página inicial, SEO). */
export function updatePage(pageId: string, payload: Record<string, unknown>): Promise<BuilderPage> {
  return privateApi<BuilderPage>(`/pages/${pageId}/`, { method: 'PATCH', body: payload })
}

/** Páginas do mesmo site — o seletor de página da topbar do editor. */
export async function fetchSitePages(siteId: string): Promise<BuilderPage[]> {
  const data = await privateApi<{ results?: BuilderPage[] } | BuilderPage[]>(`/pages/`, {
    query: { site: siteId, ordering: 'display_order' },
  })
  const rows = Array.isArray(data) ? data : (data.results ?? [])
  // A home primeiro, depois a ordem escolhida pelo cliente. É a ordem em que
  // as páginas aparecem no site, e o seletor do editor deve espelhá-la.
  return [...rows].sort((a, b) => {
    if (a.is_home !== b.is_home) return a.is_home ? -1 : 1
    return (a.display_order ?? 0) - (b.display_order ?? 0)
  })
}

/**
 * Cria uma página vazia no site.
 *
 * Nasce sem conteúdo de propósito: o cliente escolhe as seções no painel de
 * blocos. Copiar a home seria pior — ele teria de apagar tudo antes de montar
 * a página de contato.
 */
export function createPage(siteId: string, payload: { title: string; slug: string }): Promise<BuilderPage> {
  return privateApi<BuilderPage>('/pages/', {
    method: 'POST',
    body: {
      site: siteId,
      title: payload.title,
      slug: payload.slug,
      is_home: false,
      draft_data: { pages: [{ name: payload.title, frames: [{ component: { type: 'wrapper', components: [] } }] }] },
    },
  })
}

export function deletePage(pageId: string): Promise<void> {
  return privateApi<void>(`/pages/${pageId}/`, { method: 'DELETE' })
}

/** Grava o rascunho. Não publica — ver `publishPage`. */
export function saveDraft(pageId: string, project: BuilderProject): Promise<BuilderPage> {
  return privateApi<BuilderPage>(`/pages/${pageId}/`, {
    method: 'PATCH',
    body: { draft_data: project },
  })
}

export function publishPage(pageId: string): Promise<BuilderPage> {
  return privateApi<BuilderPage>(`/pages/${pageId}/publish/`, { method: 'POST' })
}

/** Payload público montado a partir do RASCUNHO — o preview antes de publicar. */
export function fetchDraftPreview(siteId: string, page?: string): Promise<StorefrontPayload> {
  return privateApi<StorefrontPayload>(`/sites/${siteId}/preview/`, {
    query: page ? { page } : undefined,
  })
}

/**
 * A allowlist que o servidor aplica ao salvar.
 *
 * O editor lê daqui em vez de manter a própria cópia. Duas listas divergindo
 * dariam o pior sintoma possível: o cliente monta a página com um bloco que o
 * editor ofereceu e recebe um erro ao salvar.
 */
export function fetchBuilderSchema(): Promise<BuilderSchemaContract> {
  return privateApi<BuilderSchemaContract>('/schema/')
}

export interface MenuOption {
  id: string
  name: string
  slug: string
  menu_type: string
}

/**
 * Menus (`menu.Menu`) da conta.
 *
 * Servem a dois campos diferentes do painel, e por isso a lista é uma só: o
 * recorte de produtos do site (por ID) e as navegações do cabeçalho (por
 * `slug`, que é o handle usado nos blocos e no payload público).
 */
export async function fetchMenus(): Promise<MenuOption[]> {
  const data = await appApi<{ results?: MenuOption[] }>('/menu/menus/')
  return data.results ?? (data as unknown as MenuOption[]) ?? []
}

/** Catálogos (`menu.Menu`) do restaurante — o recorte de produtos do site. */
export function fetchCatalogs(): Promise<Array<{ id: string; name: string }>> {
  return fetchMenus()
}

export function fetchThemePresets(): Promise<{ default: string; presets: ThemePreset[] }> {
  return privateApi<{ default: string; presets: ThemePreset[] }>('/themes/')
}
