/**
 * Estado da sessão do editor, compartilhado pelas telas de edição.
 *
 * `useState` e não um `ref` de módulo: o Nuxt isola `useState` por requisição,
 * então um servidor SSR atendendo dois visitantes ao mesmo tempo não mistura as
 * duas sessões. Um `ref` no escopo do módulo é global ao processo — é
 * exatamente o vazamento de tenant que este arquivo existe para evitar.
 *
 * A sessão é sempre buscada POR SLUG. O servidor responde 403 quando o slug não
 * é do usuário, e é essa resposta que fecha a rota — nenhuma decisão de acesso
 * é tomada aqui no navegador.
 */
import {
  crossSiteCookieWarning,
  EditorAuthError,
  fetchEditorSession,
  loginEditor,
  logoutEditor,
  refreshEditorSession,
  type EditorSession,
} from '~~/services/api/storefront-auth'

export type EditorAuthState = 'loading' | 'anonymous' | 'forbidden' | 'ready'

export function useStorefrontAuth() {
  const session = useState<EditorSession | null>('sf-editor-session', () => null)
  const state = useState<EditorAuthState>('sf-editor-auth-state', () => 'loading')
  const failure = useState<string>('sf-editor-auth-failure', () => '')

  function apply(next: EditorSession) {
    session.value = next
    state.value = 'ready'
    failure.value = ''
  }

  function reject(error: unknown) {
    const authError = error instanceof EditorAuthError ? error : null
    session.value = null
    if (authError?.isForbidden) {
      state.value = 'forbidden'
      failure.value = authError.message
      return
    }
    state.value = 'anonymous'
    // Um 401 é o caso normal de "ainda não entrou": mostrar um erro vermelho
    // para quem só abriu a página seria assustar sem motivo.
    failure.value = authError?.isUnauthenticated ? '' : (authError?.message ?? 'Falha ao verificar a sessão.')
  }

  /**
   * Resolve a sessão para um site. Chamado ao abrir qualquer tela de edição.
   *
   * Tenta a sessão, e só se ela vier 401 tenta renovar pelo refresh antes de
   * desistir — o access token dura pouco, então quem voltou no dia seguinte
   * ainda tem sessão válida e não deveria digitar a senha de novo.
   */
  async function ensureSession(siteSlug: string): Promise<void> {
    state.value = 'loading'
    try {
      apply(await fetchEditorSession(siteSlug))
      return
    } catch (error) {
      if (!(error instanceof EditorAuthError) || !error.isUnauthenticated) {
        reject(error)
        return
      }
    }

    try {
      await refreshEditorSession()
      apply(await fetchEditorSession(siteSlug))
    } catch (error) {
      reject(error)
    }
  }

  async function signIn(username: string, password: string, siteSlug: string): Promise<boolean> {
    failure.value = ''
    try {
      apply(await loginEditor(username, password, siteSlug))

      // Login 200 não garante sessão: se o editor e a API estiverem em hosts
      // diferentes, o cookie é gravado e nunca mais enviado, e o erro só
      // apareceria depois, como "não foi possível carregar" em outra tela.
      // Confirmar aqui transforma um mistério num aviso acionável.
      try {
        await fetchEditorSession(siteSlug)
      } catch (verifyError) {
        const warning = crossSiteCookieWarning()
        if (warning) {
          failure.value = warning
          state.value = 'anonymous'
          session.value = null
          return false
        }
        throw verifyError
      }

      return true
    } catch (error) {
      const authError = error instanceof EditorAuthError ? error : null
      // Aqui, ao contrário do `ensureSession`, TODO erro é para mostrar: o
      // usuário acabou de digitar algo e precisa saber o que deu errado.
      failure.value = authError?.message ?? 'Não foi possível entrar.'
      state.value = authError?.isForbidden ? 'forbidden' : 'anonymous'
      session.value = null
      return false
    }
  }

  async function signOut(): Promise<void> {
    try {
      await logoutEditor()
    } finally {
      session.value = null
      state.value = 'anonymous'
      failure.value = ''
    }
  }

  /** O site do slug atual, já confirmado pelo servidor. */
  const site = computed(() => session.value?.site ?? null)

  function can(code: string): boolean {
    return Boolean(session.value?.permissions.includes(code))
  }

  return { session, state, failure, site, ensureSession, signIn, signOut, can }
}
