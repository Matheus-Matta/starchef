/**
 * Cliente HTTP do storefront.
 *
 * Toda chamada ao Django passa por aqui — `$fetch` espalhado por dezenas de
 * componentes é como se perde o controle de base URL, credencial e tratamento
 * de erro.
 *
 * Há duas superfícies bem diferentes do outro lado, e elas não se misturam:
 *
 * - `publicApi` bate em `/api/v1/public/**`, sem credencial nenhuma. É o que o
 *   site do cliente final usa.
 * - `privateApi` bate em `/api/v1/storefront/**` com o cookie de sessão DO
 *   EDITOR (`credentials: 'include'`). Só o editor usa, e só no navegador —
 *   no SSR não existe cookie de operador para enviar.
 *
 * Toda chamada autenticada leva `X-Auth-Scope: storefront`. O editor e o painel
 * administrativo batem no mesmo backend, e cada um tem seus próprios cookies
 * (`sf_*` e `sc_*`). Sem o header, o backend teria de adivinhar qual usar
 * quando os dois estão abertos no mesmo navegador — e adivinharia errado: a
 * requisição do editor seria atendida como o operador logado no painel.
 */
import type { StorefrontPayload } from '~~/types/storefront'

export interface ApiOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  query?: Record<string, string | number | boolean | undefined>
  body?: unknown
  headers?: Record<string, string>
}

export const AUTH_SCOPE_HEADER = 'X-Auth-Scope'
export const AUTH_SCOPE = 'storefront'

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return { [AUTH_SCOPE_HEADER]: AUTH_SCOPE, ...(extra ?? {}) }
}

function apiBase(): string {
  return useRuntimeConfig().public.apiBase.replace(/\/+$/, '')
}

export async function publicApi<T>(path: string, options: ApiOptions = {}): Promise<T> {
  return $fetch<T>(`${apiBase()}/api/v1/public${path}`, {
    method: options.method ?? 'GET',
    query: options.query,
    body: options.body as Record<string, unknown> | undefined,
    headers: options.headers,
  })
}

export async function privateApi<T>(path: string, options: ApiOptions = {}): Promise<T> {
  return $fetch<T>(`${apiBase()}/api/v1/storefront${path}`, {
    method: options.method ?? 'GET',
    query: options.query,
    body: options.body as Record<string, unknown> | undefined,
    headers: authHeaders(options.headers),
    // O JWT do editor vive em cookie httpOnly (`sf_access`), então basta
    // deixar o navegador enviá-lo. Nada de token no localStorage — é o que
    // impede um XSS de roubar a sessão.
    credentials: 'include',
  })
}

/**
 * Rotas autenticadas FORA do prefixo `/storefront` (ex.: `/menu/menus/`).
 *
 * O editor precisa de um punhado delas — a lista de catálogos que alimenta a
 * vitrine, por exemplo. Mesma sessão, mesmo cookie; só o prefixo muda.
 */
export async function appApi<T>(path: string, options: ApiOptions = {}): Promise<T> {
  return $fetch<T>(`${apiBase()}/api/v1${path}`, {
    method: options.method ?? 'GET',
    query: options.query,
    body: options.body as Record<string, unknown> | undefined,
    headers: authHeaders(options.headers),
    credentials: 'include',
  })
}

export type { StorefrontPayload }
