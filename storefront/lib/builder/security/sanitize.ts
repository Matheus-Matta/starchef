/**
 * Sanitização no lado do renderer.
 *
 * O backend já sanitiza tudo ao salvar — esta camada não é a defesa principal.
 * Ela existe porque o renderer usa `v-html` para o texto rico, e `v-html` com
 * conteúdo não conferido é XSS por construção. Entre confiar que o dado que
 * chegou passou mesmo pelo servidor e conferir de novo em 40 linhas, o preço
 * de conferir é baixo demais para não pagar.
 */

const ALLOWED_SCHEMES = new Set(['http:', 'https:', 'mailto:', 'tel:'])

/**
 * Remove espaços e caracteres de controle.
 *
 * Escrito com comparação de code point em vez de uma classe de regex: o
 * navegador ignora uma quebra de linha no meio de "java(quebra)script:" e
 * executa o mesmo, então esses caracteres precisam sumir ANTES de olharmos o
 * esquema da URL — e um caractere de controle literal dentro de um regex é
 * exatamente o tipo de coisa que um editor ou um `git` normaliza sem avisar.
 */
function stripBlankAndControl(text: string): string {
  let out = ''
  for (const char of text) {
    if (char.charCodeAt(0) > 32) out += char
  }
  return out
}

/**
 * URL utilizável, ou string vazia.
 *
 * Sem esquema é caminho relativo (`/cardapio`, `#promo`, `?busca=x`) e passa.
 * `javascript:` e `data:` são recusados.
 */
export function safeUrl(value: unknown): string {
  if (value === null || value === undefined) return ''
  const text = String(value).trim()
  if (!text) return ''

  const scheme = /^([a-z][a-z0-9+.-]*):/i.exec(stripBlankAndControl(text))
  if (!scheme) return text
  return ALLOWED_SCHEMES.has(`${scheme[1].toLowerCase()}:`) ? text : ''
}

const RICH_TEXT_TAGS = 'p|br|span|strong|b|em|i|u|s|small|mark|sub|sup|a|ul|ol|li|blockquote|h[1-6]|div'
const TAG_RE = new RegExp(`<(/?)(?!(?:${RICH_TEXT_TAGS})\\b)[a-z][^>]*>`, 'gi')
const DANGEROUS_BLOCK_RE = /<(script|style|iframe|object|embed|noscript|template)\b[\s\S]*?<\/\1\s*>/gi
const SELF_CLOSING_DANGEROUS_RE = /<(script|style|iframe|object|embed|link|meta|base|input|form)\b[^>]*>/gi
const EVENT_ATTR_RE = /\son[a-z-]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi
const JS_URL_ATTR_RE = /\s(href|src|xlink:href)\s*=\s*("|')?\s*(javascript|data|vbscript):[^"'>\s]*("|')?/gi

/**
 * Devolve só o subconjunto de HTML que o texto rico pode usar.
 *
 * Tags fora da lista perdem a marcação e mantêm o texto; `script`, `style`,
 * `iframe` e companhia perdem também o conteúdo — senão o corpo de um
 * `<script>` reapareceria como texto visível na página.
 */
export function sanitizeRichText(html: unknown): string {
  if (html === null || html === undefined) return ''

  return String(html)
    .replace(DANGEROUS_BLOCK_RE, '')
    .replace(SELF_CLOSING_DANGEROUS_RE, '')
    .replace(EVENT_ATTR_RE, '')
    .replace(JS_URL_ATTR_RE, '')
    .replace(TAG_RE, '')
    .slice(0, 20000)
}

/** Texto puro: usado onde o valor vira atributo (alt, title, aria-label). */
export function plainText(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value).replace(/<[^>]*>/g, '').slice(0, 2000)
}
