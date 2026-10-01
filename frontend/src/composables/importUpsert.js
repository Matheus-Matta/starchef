import { normalizeApiError } from "../utils/apiError";

/**
 * Importar CSV: atualiza o que já existe, cria só o que falta.
 *
 * A importação só CRIAVA. Reimportar a planilha que o próprio sistema
 * exportou (o uso mais comum: exportar, ajustar preço no Excel, importar)
 * dava "Já existe um registro com estes dados (valor duplicado)" em TODAS as
 * linhas — "0 de 17 itens importados".
 *
 * A linha casa com o registro existente pela CHAVE: o código interno quando o
 * cadastro tem um, senão o código, senão o nome. Linha sem a chave é criada.
 */
const CHAVES = ["internal_code", "code", "name"];

export function importKeyFor(fields, preferred) {
  const names = new Set(fields.map((field) => field.name));
  if (preferred && names.has(preferred)) return preferred;
  return CHAVES.find((key) => names.has(key)) || null;
}

const normalizar = (value) => String(value ?? "").trim().toLowerCase();

async function existentesPorChave(service, key) {
  const porChave = new Map();
  let page = await service.list({ page_size: 500 });
  for (;;) {
    for (const row of page?.results || []) {
      const valor = normalizar(row[key]);
      if (valor && !porChave.has(valor)) porChave.set(valor, row.id);
    }
    if (!page?.next) break;
    page = await service.listByUrl(page.next);
  }
  return porChave;
}

export async function importUpsert({ service, payloads, fields, preferredKey }) {
  const key = importKeyFor(fields, preferredKey);
  const existentes = key ? await existentesPorChave(service, key) : new Map();
  const resultado = { created: 0, updated: 0, errors: [] };
  for (const [index, payload] of payloads.entries()) {
    const id = key ? existentes.get(normalizar(payload[key])) : null;
    try {
      if (id) {
        await service.update(id, payload);
        resultado.updated += 1;
      } else {
        const criado = await service.create(payload);
        resultado.created += 1;
        // Duas linhas com a mesma chave na planilha: a segunda atualiza a
        // primeira em vez de tentar criar de novo.
        if (key && criado?.id) existentes.set(normalizar(payload[key]), criado.id);
      }
    } catch (error) {
      resultado.errors.push(`Linha ${index + 2}: ${normalizeApiError(error).message}`);
    }
  }
  return resultado;
}
