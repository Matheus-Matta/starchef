/**
 * Helpers para a paginacao do Django REST Framework, que devolve URLs
 * absolutas em `next`/`previous`. Precisamos convertê-las de volta para
 * chamadas relativas do axios e derivar o numero da pagina atual.
 */

const API_PREFIX = "/api/v1";

/** Converte uma URL absoluta da API em { path, params } relativo ao baseURL do axios. */
export function parseApiUrl(url) {
  const parsed = new URL(url, window.location.origin);
  return {
    path: parsed.pathname.replace(API_PREFIX, ""),
    params: Object.fromEntries(parsed.searchParams.entries()),
  };
}

/** Deriva o numero da pagina atual a partir das URLs previous/next. */
export function pageFromUrls(previous, next) {
  const nextPage = readPageParam(next);
  if (nextPage) return nextPage - 1;

  const previousPage = readPageParam(previous);
  if (previousPage) return previousPage + 1;

  return 1;
}

function readPageParam(url) {
  if (!url) return null;
  const parsed = new URL(url, window.location.origin);
  return Number(parsed.searchParams.get("page") || 1);
}
