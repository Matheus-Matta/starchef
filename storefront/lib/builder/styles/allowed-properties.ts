/**
 * Propriedades de CSS que sobrevivem à compilação.
 *
 * Esta lista é a segunda barreira, não a primeira: o backend já valida e
 * reescreve o projeto ao salvar (`apps/storefront/builder_schema.py`). Ela
 * existe porque o renderer também roda sobre dados que podem ter chegado por
 * outro caminho — um preview de rascunho, um payload em cache antigo, uma
 * resposta adulterada em trânsito — e o site público nunca deve emitir CSS que
 * ninguém autorizou.
 *
 * Manter as duas listas parecidas é intencional. Divergirem não quebra a
 * segurança (a do servidor é a que grava), só faz uma propriedade salva não
 * aparecer no site.
 */

export const ALLOWED_STYLE_PROPERTIES = new Set([
  // dimensões
  'width', 'max-width', 'min-width', 'height', 'max-height', 'min-height', 'aspect-ratio',
  // espaçamento
  'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
  'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
  'gap', 'row-gap', 'column-gap',
  // layout
  'display', 'flex-direction', 'flex-wrap', 'flex', 'flex-grow', 'flex-shrink', 'flex-basis',
  'justify-content', 'align-items', 'align-self', 'align-content', 'order',
  'grid-template-columns', 'grid-template-rows', 'grid-column', 'grid-row', 'grid-auto-flow',
  'position', 'top', 'right', 'bottom', 'left', 'z-index',
  'overflow', 'overflow-x', 'overflow-y', 'float', 'clear', 'visibility',
  // fundo e borda
  'background', 'background-color', 'background-image', 'background-size',
  'background-position', 'background-repeat', 'background-attachment',
  'border', 'border-top', 'border-right', 'border-bottom', 'border-left',
  'border-color', 'border-width', 'border-style', 'border-radius',
  'border-top-left-radius', 'border-top-right-radius',
  'border-bottom-left-radius', 'border-bottom-right-radius',
  'box-shadow', 'outline',
  // tipografia
  'color', 'font-family', 'font-size', 'font-weight', 'font-style',
  'line-height', 'letter-spacing', 'word-spacing', 'text-align', 'text-decoration',
  'text-transform', 'text-shadow', 'white-space', 'word-break', 'text-overflow',
  'list-style', 'list-style-type',
  // imagem e efeitos
  'object-fit', 'object-position', 'opacity', 'filter', 'mix-blend-mode',
  'transform', 'transform-origin', 'transition', 'animation', 'cursor',
  'pointer-events', 'user-select',
])

/** Construções de CSS que executam código ou buscam recurso externo arbitrário. */
const FORBIDDEN_VALUE = /(expression\s*\(|javascript\s*:|vbscript\s*:|@import|behavior\s*:|-moz-binding|<\/)/i

/** `backgroundColor` → `background-color` (o editor emite os dois formatos). */
export function toKebabCase(name: string): string {
  return name.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()
}

export function sanitizeStyleMap(style: Record<string, unknown> | undefined | null): Record<string, string> {
  if (!style || typeof style !== 'object') return {}

  const clean: Record<string, string> = {}
  for (const [rawName, rawValue] of Object.entries(style)) {
    const name = toKebabCase(rawName)
    if (!ALLOWED_STYLE_PROPERTIES.has(name)) continue
    if (rawValue === null || rawValue === undefined) continue

    const value = String(rawValue).trim().slice(0, 500)
    if (!value || FORBIDDEN_VALUE.test(value)) continue
    clean[name] = value
  }
  return clean
}
