// Os tokens JWT ficam em cookies httpOnly (não legíveis por JS, por segurança).
// O JS só enxerga a flag `sc_session` (legível) que sinaliza sessão ativa.
const SESSION_FLAG = "sc_session";
const SESSION_FLAG_MAX_AGE = 7 * 24 * 60 * 60;

export function getCookie(name) {
  const escaped = name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1");
  const match = document.cookie.match(new RegExp("(?:^|; )" + escaped + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Há sessão ativa? (flag legível gravada pelo backend no login). */
export function hasSession() {
  return Boolean(getCookie(SESSION_FLAG));
}

/**
 * Grava a flag de sessão NESTE origin, logo após o login dar certo.
 *
 * O backend também grava `sc_session`, mas no host da API. Com a API em outro
 * host (app.dominio -> api.dominio) esse cookie é host-only lá e o frontend
 * nunca o enxerga: `hasSession()` daria falso e todo F5 cairia no login, mesmo
 * com os cookies httpOnly válidos. Na mesma origem é o mesmo cookie do
 * backend, apenas reafirmado. Vive o tempo do refresh (7 dias).
 */
export function markSession() {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${SESSION_FLAG}=1; Max-Age=${SESSION_FLAG_MAX_AGE}; path=/; SameSite=Lax${secure}`;
}

/** Remove a flag de sessão localmente (os cookies httpOnly o backend limpa no logout). */
export function clearSession() {
  const expire = "; Max-Age=0; path=/";
  document.cookie = `${SESSION_FLAG}=${expire}`;
  // O backend pode gravar o cookie com Domain (DJANGO_AUTH_COOKIE_DOMAIN, usado
  // quando a API vive num subdomínio). Sem repetir o mesmo Domain o delete não
  // casa com o cookie existente e a flag sobrevive ao logout — então varremos
  // também os domínios-pai do host atual.
  const parts = window.location.hostname.split(".");
  for (let i = 0; i < parts.length - 1; i += 1) {
    const domain = parts.slice(i).join(".");
    document.cookie = `${SESSION_FLAG}=${expire}; domain=${domain}`;
    document.cookie = `${SESSION_FLAG}=${expire}; domain=.${domain}`;
  }
}
