// Os tokens JWT ficam em cookies httpOnly (não legíveis por JS, por segurança).
// O JS só enxerga a flag `sc_session` (legível) que sinaliza sessão ativa.
const SESSION_FLAG = "sc_session";

export function getCookie(name) {
  const escaped = name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1");
  const match = document.cookie.match(new RegExp("(?:^|; )" + escaped + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Há sessão ativa? (flag legível gravada pelo backend no login). */
export function hasSession() {
  return Boolean(getCookie(SESSION_FLAG));
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
