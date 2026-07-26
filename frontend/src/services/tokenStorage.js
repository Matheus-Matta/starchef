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
  document.cookie = `${SESSION_FLAG}=; Max-Age=0; path=/`;
}
