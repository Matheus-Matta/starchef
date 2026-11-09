/**
 * Que tipo de entrada um filtro usa, e com quais valores fixos.
 *
 * Valor fixo sempre que der: escolher "Bebidas" numa lista é mais rápido e
 * não erra como digitar o id da categoria. A ordem de onde as opções vêm:
 *   1. as do próprio campo (`options` de um dropdown);
 *   2. as buscadas do cadastro relacionado (`remote-dropdown`: categoria, setor...);
 *   3. os rótulos da coluna da lista com o mesmo nome (`map`: situação, tipo...).
 *
 * Os valores viram TEXTO: o filtro mora na URL (`?f_status=paid`), e a opção
 * numérica `12` precisa casar com o `"12"` que volta de lá.
 */
export const SEM_FILTRO = "";
const NUMERICOS = new Set(["number", "decimal", "money", "percent"]);
const DATAS = new Set(["date", "datetime"]);
const REMOTOS = new Set(["remote-dropdown", "remote-multiselect"]);

const comoOpcoes = (lista) => (lista || []).map((opcao) => ({ label: String(opcao.label), value: String(opcao.value) }));

export function opcoesDoFiltro(campo, { colunas = [], remotas = {} } = {}) {
  if (campo.options?.length) return comoOpcoes(campo.options);
  if (REMOTOS.has(campo.type)) return comoOpcoes(remotas[campo.name]);
  const coluna = colunas.find((item) => item.key === campo.name && item.map);
  if (coluna) return comoOpcoes(Object.entries(coluna.map).map(([value, label]) => ({ value, label })));
  return [];
}

/** "lista" | "simnao" | "numero" | "data" | "texto" */
export function tipoDoFiltro(campo, opcoes) {
  if (opcoes.length || REMOTOS.has(campo.type)) return "lista";
  if (campo.type === "boolean") return "simnao";
  if (NUMERICOS.has(campo.type)) return "numero";
  if (DATAS.has(campo.type)) return "data";
  return "texto";
}

export const ehRemoto = (campo) => REMOTOS.has(campo.type) && Boolean(campo.endpoint);
