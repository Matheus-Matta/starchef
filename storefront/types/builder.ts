/**
 * Tipos do schema de renderização — a saída do compiler.
 *
 * O `RenderNode` é o contrato entre o editor e o site público. É de propósito
 * mais pobre que o project data do GrapesJS: só o que o renderer Vue precisa
 * para desenhar. É isso que permite trocar o editor um dia sem reescrever o
 * site.
 */

export type Breakpoint = 'desktop' | 'tablet' | 'mobile'

export type StyleMap = Record<string, string>

export type ResponsiveStyles = Partial<Record<Breakpoint, StyleMap>>

export interface RenderNode {
  /** Estável entre renders (vem do id do componente ou do caminho na árvore). */
  id: string
  type: string
  tag: string
  /** Configuração do bloco (categoria, colunas, mostrar preço…). */
  props: Record<string, unknown>
  /** Atributos HTML já sanitizados (href, alt, src…). */
  attrs: Record<string, string>
  /** HTML de texto rico, já sanitizado pelo backend e revalidado aqui. */
  content: string
  classes: string[]
  styles: ResponsiveStyles
  children: RenderNode[]
}

export interface RenderSchema {
  schemaVersion: number
  nodes: RenderNode[]
  /** CSS pronto para um único `<style>`, já com as media queries. */
  css: string
}
