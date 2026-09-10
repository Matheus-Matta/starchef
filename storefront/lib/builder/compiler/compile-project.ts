/**
 * Compiler: project data do GrapesJS → schema de renderização.
 *
 * É a peça que desacopla o editor do site. O GrapesJS guarda muita coisa que
 * só interessa a ele (estado de seleção, flags de edição, regras de CSS soltas
 * por seletor); o site público precisa de uma árvore simples de nós tipados com
 * estilos já resolvidos por breakpoint.
 *
 * O que ganhamos com essa tradução:
 *
 * - o bundle público não carrega uma linha de GrapesJS;
 * - o SSR renderiza componentes Vue de verdade, com dados reais de produto,
 *   em vez de despejar HTML exportado;
 * - trocar o editor um dia não obriga a reescrever o site;
 * - nada além da allowlist de CSS chega ao navegador do cliente final.
 *
 * As regras de `styles[]` são casadas com os nós por `#id` e `.classe`, e a
 * media query de cada regra decide se ela é desktop, tablet ou mobile.
 */
import type { BuilderComponent, BuilderProject, BuilderStyleRule } from '~~/types/storefront'
import type { Breakpoint, RenderNode, RenderSchema, StyleMap } from '~~/types/builder'
import { ALL_COMPONENT_TYPES, BUILTIN_TYPES, DEFAULT_TAGS } from '../registry/components'
import { breakpointFromMedia, MOBILE_MAX_WIDTH, TABLET_MAX_WIDTH } from '../devices/devices'
import { sanitizeStyleMap } from '../styles/allowed-properties'
import { plainText, safeUrl, sanitizeRichText } from '../security/sanitize'
import { BUILDER_SCHEMA_VERSION, unwrapProject } from '../schema/version'

const KNOWN_TYPES = new Set<string>([...ALL_COMPONENT_TYPES, ...BUILTIN_TYPES])
const URL_ATTRIBUTES = new Set(['href', 'src', 'srcset', 'poster'])
const MAX_NODES = 5000

/** Regras de CSS agrupadas por seletor, já separadas por breakpoint. */
type RuleIndex = Map<string, Partial<Record<Breakpoint, StyleMap>>>

function indexStyleRules(rules: BuilderStyleRule[] | undefined): RuleIndex {
  const index: RuleIndex = new Map()
  if (!Array.isArray(rules)) return index

  for (const rule of rules) {
    const style = sanitizeStyleMap(rule?.style)
    if (!Object.keys(style).length) continue

    // Regras com `state` (`:hover`, `:focus`) não entram: o renderer aplica
    // estilo por nó, e um estado precisaria de uma folha de estilo à parte.
    // Deixar entrar aqui aplicaria o hover como se fosse o estilo normal.
    if (rule.state) continue

    const breakpoint = breakpointFromMedia(rule.mediaText)
    for (const selector of rule.selectors ?? []) {
      const key = String(selector)
      const entry = index.get(key) ?? {}
      entry[breakpoint] = { ...(entry[breakpoint] ?? {}), ...style }
      index.set(key, entry)
    }
  }
  return index
}

function mergeStyles(
  target: Partial<Record<Breakpoint, StyleMap>>,
  source: Partial<Record<Breakpoint, StyleMap>> | undefined,
): void {
  if (!source) return
  for (const breakpoint of ['desktop', 'tablet', 'mobile'] as Breakpoint[]) {
    if (!source[breakpoint]) continue
    target[breakpoint] = { ...(target[breakpoint] ?? {}), ...source[breakpoint] }
  }
}

function compileAttributes(component: BuilderComponent): Record<string, string> {
  const attrs: Record<string, string> = {}
  for (const [name, value] of Object.entries(component.attributes ?? {})) {
    if (value === null || value === undefined) continue
    // `on*` nunca deveria chegar aqui (o backend recusa), mas o renderer
    // repassa atributos direto para o DOM — a checagem custa uma linha.
    if (/^on/i.test(name)) continue
    if (name === 'style' || name === 'id') continue

    if (URL_ATTRIBUTES.has(name)) {
      const url = safeUrl(value)
      if (url) attrs[name] = url
      continue
    }
    attrs[name] = plainText(value)
  }
  return attrs
}

function compileComponent(
  component: BuilderComponent | string,
  rules: RuleIndex,
  path: string,
  counter: { value: number },
): RenderNode | null {
  if (counter.value >= MAX_NODES) return null

  // Um filho pode ser texto puro no project data do GrapesJS.
  if (typeof component === 'string') {
    const content = sanitizeRichText(component)
    if (!content.trim()) return null
    counter.value += 1
    return {
      id: path,
      type: 'sf-text',
      tag: 'span',
      props: {},
      attrs: {},
      content,
      classes: [],
      styles: {},
      children: [],
    }
  }

  if (!component || typeof component !== 'object') return null

  const type = component.type || 'wrapper'
  // Fail closed: um tipo que o renderer não conhece some da página em vez de
  // virar um `<div>` genérico. Um bloco desconhecido não tem como desenhar
  // certo, e um retângulo vazio no lugar dele é mais fácil de diagnosticar do
  // que um layout sutilmente errado.
  if (!KNOWN_TYPES.has(type)) return null

  counter.value += 1

  const styles: Partial<Record<Breakpoint, StyleMap>> = {}
  const inline = sanitizeStyleMap(component.style)
  if (Object.keys(inline).length) styles.desktop = inline

  const componentId = typeof component.attributes?.id === 'string' ? component.attributes.id : ''
  const classes = (component.classes ?? []).map((name) => String(name)).filter(Boolean)

  // Regras por classe primeiro, depois por id: o id é mais específico, então
  // vence a classe — a mesma ordem que o navegador aplicaria.
  for (const className of classes) mergeStyles(styles, rules.get(`.${className}`))
  if (componentId) mergeStyles(styles, rules.get(`#${componentId}`))

  const children: RenderNode[] = []
  const rawChildren = Array.isArray(component.components) ? component.components : []
  rawChildren.forEach((child, index) => {
    const compiled = compileComponent(child, rules, `${path}-${index}`, counter)
    if (compiled) children.push(compiled)
  })

  return {
    id: componentId || path,
    type,
    tag: component.tagName || DEFAULT_TAGS[type] || 'div',
    props: (component.props ?? {}) as Record<string, unknown>,
    attrs: compileAttributes(component),
    content: sanitizeRichText(component.content ?? ''),
    classes,
    styles,
    children,
  }
}

function styleMapToCss(style: StyleMap): string {
  return Object.entries(style)
    .map(([property, value]) => `${property}:${value}`)
    .join(';')
}

/**
 * CSS de todos os nós em um bloco só.
 *
 * Cada nó ganha a classe `sf-n-<id>`, e os estilos viram regras de verdade em
 * vez de `style=""` inline. Assim as media queries funcionam (atributo inline
 * não tem breakpoint) e o SSR entrega a página já estilizada, sem o pulo de
 * layout que apareceria se o CSS chegasse depois.
 */
function collectCss(nodes: RenderNode[]): string {
  const desktop: string[] = []
  const tablet: string[] = []
  const mobile: string[] = []

  const walk = (node: RenderNode) => {
    const selector = `.sf-n-${cssEscape(node.id)}`
    if (node.styles.desktop) desktop.push(`${selector}{${styleMapToCss(node.styles.desktop)}}`)
    if (node.styles.tablet) tablet.push(`${selector}{${styleMapToCss(node.styles.tablet)}}`)
    if (node.styles.mobile) mobile.push(`${selector}{${styleMapToCss(node.styles.mobile)}}`)
    node.children.forEach(walk)
  }
  nodes.forEach(walk)

  const parts = [desktop.join('')]
  if (tablet.length) parts.push(`@media (max-width:${TABLET_MAX_WIDTH}px){${tablet.join('')}}`)
  if (mobile.length) parts.push(`@media (max-width:${MOBILE_MAX_WIDTH}px){${mobile.join('')}}`)
  return parts.filter(Boolean).join('')
}

/** Deixa o id utilizável como classe CSS (o GrapesJS gera ids como `i3kf`). */
export function cssEscape(value: string): string {
  return String(value).replace(/[^A-Za-z0-9_-]/g, '-')
}

/**
 * Compila o project data publicado em um schema pronto para renderizar.
 *
 * Nunca lança: uma página malformada vira uma página vazia. O site do
 * restaurante fora do ar por causa de um nó estranho seria pior do que uma
 * seção faltando.
 */
export function compileProject(data: unknown): RenderSchema {
  const project = unwrapProject(data) as BuilderProject
  const rules = indexStyleRules(project.styles)
  const counter = { value: 0 }

  const nodes: RenderNode[] = []
  const frames = project.pages?.[0]?.frames ?? []

  frames.forEach((frame, frameIndex) => {
    const root = frame?.component
    if (!root) return

    // O `wrapper` é o contêiner do canvas do editor, não um elemento do site:
    // renderizá-lo criaria uma `<div>` a mais envolvendo a página inteira.
    const rootChildren = root.type === 'wrapper' || !root.type ? (root.components ?? []) : [root]
    rootChildren.forEach((child, index) => {
      const compiled = compileComponent(child, rules, `f${frameIndex}-${index}`, counter)
      if (compiled) nodes.push(compiled)
    })
  })

  return {
    schemaVersion: BUILDER_SCHEMA_VERSION,
    nodes,
    css: collectCss(nodes),
  }
}
