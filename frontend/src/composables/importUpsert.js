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

async function todasAsLinhas(servico) {
  const linhas = [];
  let page = await servico.list({ page_size: 500 });
  for (;;) {
    linhas.push(...(page?.results || []));
    if (!page?.next) return linhas;
    page = await servico.listByUrl(page.next);
  }
}

/**
 * Colunas de RELAÇÃO (perfil fiscal, categoria, setor, restaurantes) aceitam o
 * id OU o nome. O id exportado envelhece: reimportar os perfis fiscais cria
 * ids novos, e a planilha de produtos ficava apontando para um que não existe
 * — "Pk inválido ... objeto não existe" derrubava a linha inteira.
 *
 * Valor que não casa com nada sai do payload (o registro mantém o que já
 * tinha) e vira AVISO, não erro: o resto da linha ainda vale.
 */
async function resolverRelacoes({ fields, payloads, servicoPara }) {
  const avisos = [];
  const relacoes = fields.filter((f) => ["remote-dropdown", "remote-multiselect"].includes(f.type) && f.endpoint);
  for (const campo of relacoes) {
    if (!payloads.some((p) => p[campo.name] != null)) continue;
    const valorDe = (row) => String(row[campo.optionValue || "id"]);
    const linhas = await todasAsLinhas(servicoPara(campo));
    const ids = new Set(linhas.map(valorDe));
    const porNome = new Map(linhas.map((row) => [normalizar(row[campo.optionLabel || "name"]), valorDe(row)]));
    const resolver = (valor) => (ids.has(String(valor)) ? String(valor) : porNome.get(normalizar(valor)) ?? null);

    for (const [index, payload] of payloads.entries()) {
      const bruto = payload[campo.name];
      if (bruto == null) continue;
      const valores = Array.isArray(bruto) ? bruto : [bruto];
      const achados = valores.map(resolver);
      const faltando = valores.filter((_, i) => achados[i] == null);
      if (faltando.length) {
        avisos.push(`Linha ${index + 2}: ${campo.label} "${faltando.join(", ")}" não existe — mantido o valor atual.`);
      }
      const validos = achados.filter((v) => v != null);
      if (!validos.length) delete payload[campo.name];
      else payload[campo.name] = Array.isArray(bruto) ? validos : validos[0];
    }
  }
  return avisos;
}

/**
 * Importação em SEGUNDO PLANO: resolve as relações aqui (leituras rápidas) e
 * entrega o lote inteiro ao servidor numa chamada só.
 *
 * O `importUpsert` acima gravava linha a linha do navegador e a tela ficava
 * presa até a última. Agora o `POST /imports/` responde na hora e o worker
 * processa; o resultado chega pelo sino de notificações.
 */
export async function enviarImportacao({ api, endpoint, payloads, fields, preferredKey, servicoPara }) {
  const key = importKeyFor(fields, preferredKey);
  const warnings = servicoPara ? await resolverRelacoes({ fields, payloads, servicoPara }) : [];
  const { data } = await api.post("/imports/", { endpoint, key, rows: payloads });
  return { job: data, warnings };
}
