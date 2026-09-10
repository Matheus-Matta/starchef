/** Deixa o navegador gerar o Content-Type multipart com o boundary correto. */
export function prepareMultipartHeaders(config) {
  if (typeof FormData === "undefined" || !(config.data instanceof FormData)) return;

  const headers = config.headers;
  if (!headers) return;
  if (typeof headers.delete === "function") {
    headers.delete("Content-Type");
    return;
  }
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === "content-type") delete headers[key];
  }
}
