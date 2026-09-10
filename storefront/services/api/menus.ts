/**
 * Menus e seus itens, do editor.
 *
 * O que um bloco MOSTRA muitas vezes não está no bloco: está no menu que ele
 * aponta. O carrossel da capa é um menu de banners, o rodapé são menus de
 * links, a vitrine curada é um menu de produtos. Até aqui, trocar a foto de um
 * banner exigia sair do editor, abrir o painel administrativo, achar "Itens de
 * menu" e voltar — para uma alteração que se vê no canvas.
 *
 * Estas funções existem para fechar esse caminho. Batem em `/api/v1/menu/**`
 * com a MESMA sessão do editor (`appApi`, cookie `sf_*` + `X-Auth-Scope`), e o
 * backend já as autoriza por `storefront.edit` — o mesmo código de permissão
 * que libera a edição da página.
 *
 * A foto sobe em `multipart/form-data`, não em JSON: `MenuItem.image` é um
 * `ImageField`, e binário não cabe num corpo JSON. Por isso estas chamadas
 * usam `$fetch` direto com `FormData`, em vez do `appApi` (que serializa em
 * JSON) — a diferença é o `Content-Type`, que o navegador precisa montar
 * sozinho para incluir o `boundary`.
 */
import { AUTH_SCOPE, AUTH_SCOPE_HEADER, appApi } from './client'

export interface MenuSummary {
  id: string
  name: string
  slug: string
  menu_type: string
  source: string
  items_count?: number
}

export interface MenuItemRecord {
  id: string
  menu: string
  parent: string | null
  item_type: 'product' | 'category' | 'image' | 'custom'
  title: string
  subtitle: string
  /** URL absoluta da foto salva, ou `null`. É read-only: escrever é upload. */
  image: string | null
  url: string
  opens_in_new_tab: boolean
  display_order: number
  is_active: boolean
  product: string | null
  category: string | null
  /** O rótulo que o site usa: o título, ou o nome do produto/categoria. */
  label: string
  product_name?: string | null
  category_name?: string | null
}

/** Os campos que o editor deixa alterar. Alvo (produto/categoria) fica no painel. */
export interface MenuItemDraft {
  title?: string
  subtitle?: string
  url?: string
  display_order?: number
  is_active?: boolean
  opens_in_new_tab?: boolean
  item_type?: MenuItemRecord['item_type']
  menu?: string
  /** Arquivo novo. Ausente mantém a foto que já está salva. */
  image?: File | null
}

function apiBase(): string {
  return useRuntimeConfig().public.apiBase.replace(/\/+$/, '')
}

/**
 * Monta o corpo multipart.
 *
 * `image` só entra quando há arquivo NOVO: num PATCH parcial, a chave ausente
 * preserva a foto salva. Mandar a chave vazia apagaria a imagem do banner só
 * porque o cliente editou o título.
 */
function toFormData(draft: MenuItemDraft): FormData {
  const body = new FormData()
  for (const [key, value] of Object.entries(draft)) {
    if (key === 'image') continue
    if (value === undefined || value === null) continue
    body.append(key, typeof value === 'boolean' ? String(value) : String(value))
  }
  if (draft.image instanceof File) body.append('image', draft.image)
  return body
}

function upload<T>(path: string, method: 'POST' | 'PATCH', draft: MenuItemDraft): Promise<T> {
  return $fetch<T>(`${apiBase()}/api/v1${path}`, {
    method,
    body: toFormData(draft),
    // Sem `Content-Type` de propósito: quem o define é o navegador, que
    // precisa acrescentar o `boundary` do multipart. Escrevê-lo à mão faz o
    // Django receber um corpo que não consegue separar em campos.
    headers: { [AUTH_SCOPE_HEADER]: AUTH_SCOPE },
    credentials: 'include',
  })
}

export async function fetchMenuSummaries(): Promise<MenuSummary[]> {
  const data = await appApi<{ results?: MenuSummary[] }>('/menu/menus/')
  return data.results ?? (data as unknown as MenuSummary[]) ?? []
}

/** Itens de um menu, na ordem em que o site os mostra. */
export async function fetchMenuItems(menuId: string): Promise<MenuItemRecord[]> {
  const data = await appApi<{ results?: MenuItemRecord[] }>('/menu/menu-items/', {
    // 100 é o teto do paginador. Um menu com mais itens que isso não é um
    // menu — é um catálogo, e catálogo se edita no painel, não aqui.
    query: { menu: menuId, page_size: 100, ordering: 'display_order' },
  })
  const rows = data.results ?? (data as unknown as MenuItemRecord[]) ?? []
  return [...rows].sort((a, b) => a.display_order - b.display_order)
}

export function createMenuItem(draft: MenuItemDraft): Promise<MenuItemRecord> {
  return upload<MenuItemRecord>('/menu/menu-items/', 'POST', draft)
}

export function updateMenuItem(id: string, draft: MenuItemDraft): Promise<MenuItemRecord> {
  return upload<MenuItemRecord>(`/menu/menu-items/${id}/`, 'PATCH', draft)
}

export function deleteMenuItem(id: string): Promise<void> {
  return appApi<void>(`/menu/menu-items/${id}/`, { method: 'DELETE' })
}
