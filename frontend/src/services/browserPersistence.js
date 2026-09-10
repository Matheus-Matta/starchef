const COOKIE_MAX_AGE_SECONDS = 400 * 24 * 60 * 60;
const USE_COOKIES = import.meta.env.PROD;

function readLocalStorage(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function removeLocalStorage(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // Armazenamento bloqueado: não há legado que possamos limpar.
  }
}

function readCookie(key) {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(key)}=`;
  const entry = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null;
}

function writeCookie(key, value) {
  if (typeof document === "undefined") return;
  document.cookie = [
    `${encodeURIComponent(key)}=${encodeURIComponent(value)}`,
    `Max-Age=${COOKIE_MAX_AGE_SECONDS}`,
    "Path=/",
    "SameSite=Lax",
    "Secure",
  ].join("; ");
}

function removeCookie(key) {
  if (typeof document === "undefined") return;
  document.cookie = [
    `${encodeURIComponent(key)}=`,
    "Max-Age=0",
    "Path=/",
    "SameSite=Lax",
    "Secure",
  ].join("; ");
}

/**
 * Preferências pequenas do navegador.
 *
 * Em produção, usa exclusivamente cookies Secure. A leitura do localStorage
 * existe só para migrar instalações antigas e remove o valor legado na hora.
 * Em desenvolvimento, preserva o localStorage para funcionar em HTTP local.
 */
export function getBrowserValue(key) {
  if (!USE_COOKIES) return readLocalStorage(key);
  const value = readCookie(key);
  if (value !== null) return value;

  const legacyValue = readLocalStorage(key);
  if (legacyValue !== null) {
    writeCookie(key, legacyValue);
    removeLocalStorage(key);
  }
  return legacyValue;
}

export function setBrowserValue(key, value) {
  const normalized = String(value);
  if (USE_COOKIES) {
    writeCookie(key, normalized);
    removeLocalStorage(key);
    return;
  }
  try {
    localStorage.setItem(key, normalized);
  } catch {
    // Preferência não persistida; a aplicação continua operando nesta aba.
  }
}

export function removeBrowserValue(key) {
  if (USE_COOKIES) removeCookie(key);
  removeLocalStorage(key);
}
