/**
 * Sessão do editor.
 *
 * O editor abre por endereço público (`/burger/editor/`), então o slug do site
 * é entrada do usuário — qualquer um pode digitar outro. Quem decide se aquele
 * site é dele é o SERVIDOR: toda chamada aqui manda o slug junto, e o backend
 * responde 403 quando ele não bate com o restaurante do usuário. O front nunca
 * "confia e mostra"; ele pergunta e obedece.
 *
 * Os cookies são `sf_*`, separados dos `sc_*` do painel, para que as duas
 * sessões possam existir no mesmo navegador sem uma derrubar a outra. Eles são
 * httpOnly: este arquivo nunca vê o token, só o resultado da chamada.
 */
import { AUTH_SCOPE, AUTH_SCOPE_HEADER } from './client'

export interface EditorSiteRef {
  id: string
  slug: string
  name: string
  is_active: boolean
}

export interface EditorSession {
  user: {
    id: string
    username: string
    name: string
    email: string
    is_superuser: boolean
    is_account_admin: boolean
  }
  account_id: string | null
  account_name: string | null
  restaurant_id: string | null
  restaurant_name: string | null
  enabled_modules: string[]
  /** Só os códigos `storefront.*` — o editor não decide nada com os outros. */
  permissions: string[]
  /** Sites que ESTE usuário pode editar. Nunca de outro restaurante. */
  sites: EditorSiteRef[]
  /** Presente quando a chamada informou um slug e ele foi aceito. */
  site?: EditorSiteRef
}

/** Erro de sessão já traduzido para o que a tela precisa decidir. */
export class EditorAuthError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
    this.name = 'EditorAuthError'
  }

  /** 401: não há sessão. A tela mostra o formulário de entrada. */
  get isUnauthenticated() {
    return this.status === 401
  }

  /** 403: há sessão, mas este site não é dele (ou falta permissão/módulo). */
  get isForbidden() {
    return this.status === 403
  }
}

function authBase(): string {
  const base = String(useRuntimeConfig().public.apiBase).replace(/\/+$/, '')
  return `${base}/api/v1/storefront/auth`
}

/** Mensagem legível de dentro do envelope de erro da API. */
function messageOf(error: unknown, fallback: string): string {
  const data = (error as { data?: Record<string, unknown> })?.data
  const envelope = data?.error as { message?: unknown } | undefined
  const message = envelope?.message ?? data?.detail
  if (typeof message === 'string' && message.trim()) return message
  // O DRF às vezes aninha `{detail: "..."}` dentro de `message`.
  if (message && typeof message === 'object') {
    const detail = (message as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  return fallback
}

function toAuthError(error: unknown, fallback: string): EditorAuthError {
  const status = Number((error as { status?: number; statusCode?: number })?.status
    ?? (error as { statusCode?: number })?.statusCode ?? 0)
  return new EditorAuthError(status, messageOf(error, fallback))
}

async function call<T>(path: string, options: { method?: 'GET' | 'POST'; body?: unknown; query?: Record<string, string> }, fallback: string): Promise<T> {
  try {
    return await $fetch<T>(`${authBase()}${path}`, {
      method: options.method ?? 'GET',
      body: options.body as Record<string, unknown> | undefined,
      query: options.query,
      headers: { [AUTH_SCOPE_HEADER]: AUTH_SCOPE },
      credentials: 'include',
    })
  } catch (error) {
    throw toAuthError(error, fallback)
  }
}

export function loginEditor(username: string, password: string, site?: string): Promise<EditorSession> {
  return call<EditorSession>(
    '/login/',
    { method: 'POST', body: { username, password, ...(site ? { site } : {}) } },
    'Não foi possível entrar. Confira usuário e senha.',
  )
}

/** Quem sou eu — e, com `site`, "este endereço é meu?" (403 quando não é). */
export function fetchEditorSession(site?: string): Promise<EditorSession> {
  return call<EditorSession>(
    '/session/',
    { method: 'GET', query: site ? { site } : undefined },
    'Não foi possível verificar a sessão.',
  )
}

/**
 * Renova o access token pelo refresh que está no cookie.
 *
 * Vale a tentativa antes de mostrar o formulário: o access dura pouco e o
 * refresh dura dias, então quem voltou no dia seguinte tem 401 na sessão mas
 * ainda tem sessão de verdade — pedir a senha ali seria pedir à toa.
 */
export function refreshEditorSession(): Promise<{ detail: string }> {
  return call<{ detail: string }>('/refresh/', { method: 'POST' }, 'Sessão expirada.')
}

export function logoutEditor(): Promise<void> {
  return call<void>('/logout/', { method: 'POST' }, 'Não foi possível sair.')
}

/**
 * O endereço do editor e o da API são do MESMO site?
 *
 * Os cookies de sessão são `SameSite=Lax`, o que significa que o navegador NÃO
 * os envia em requisições de origem cruzada de site diferente. Abrir o editor
 * em `127.0.0.1:3100` apontando para uma API em `localhost:8001` produz o pior
 * sintoma possível: o login responde 200, os cookies são gravados, e a
 * requisição seguinte volta 401 — sem nada no console que explique por quê.
 * Porta diferente não é problema; HOST diferente é.
 *
 * Devolve a mensagem do problema, ou string vazia quando está tudo certo.
 */
export function crossSiteCookieWarning(): string {
  if (typeof window === 'undefined') return ''

  let apiHost = ''
  try {
    apiHost = new URL(String(useRuntimeConfig().public.apiBase)).hostname
  } catch {
    return ''
  }

  const pageHost = window.location.hostname
  if (!apiHost || apiHost === pageHost) return ''

  // Subdomínios do mesmo domínio registrável (`app.casa.com` e `api.casa.com`)
  // são o MESMO site e funcionam — não vale avisar sobre eles.
  const registrable = (host: string) => host.split('.').slice(-2).join('.')
  if (registrable(apiHost) === registrable(pageHost) && apiHost.includes('.') && pageHost.includes('.')) return ''

  return (
    `O editor está em "${pageHost}" e a API em "${apiHost}". ` +
    'São sites diferentes para o navegador, então o cookie de sessão não é enviado ' +
    'e o login não se mantém. Use o mesmo host nos dois endereços.'
  )
}
