/**
 * Versão do schema do builder.
 *
 * Todo rascunho salvo carrega este número. Quando o formato mudar, uma
 * migration em `lib/builder/migrations/` converte os projetos antigos ao
 * carregar — sem isso, uma mudança de formato quebraria de vez toda página já
 * montada por um cliente, e não há como pedir a ele que "salve de novo".
 */
export const BUILDER_SCHEMA_VERSION = 1

export interface BuilderEnvelope {
  schemaVersion: number
  project: Record<string, unknown>
}

/**
 * Aceita tanto o envelope (`{schemaVersion, project}`) quanto o project data
 * cru — sites criados antes do envelope existir, e o `published_data` que o
 * backend semeia no provisionamento, chegam sem ele.
 */
export function unwrapProject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object') return {}
  const record = value as Record<string, unknown>
  if (record.project && typeof record.project === 'object') {
    return record.project as Record<string, unknown>
  }
  return record
}

export function wrapProject(project: Record<string, unknown>): BuilderEnvelope {
  return { schemaVersion: BUILDER_SCHEMA_VERSION, project }
}
