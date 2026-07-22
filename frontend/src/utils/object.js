/** Helpers de acesso a dados aninhados usados pelas tabelas/detalhes. */

/** Acessa um valor aninhado por caminho com ponto. Ex.: getByPath(obj, "profile.branch_name"). */
export function getByPath(obj, path) {
  return String(path)
    .split(".")
    .reduce((acc, key) => (acc == null ? acc : acc[key]), obj);
}

/**
 * Resolve o valor de uma coluna/campo de um registro:
 * usa `column.value(row)` quando definido, senao acessa `column.key` por caminho.
 */
export function resolveColumnValue(row, column) {
  return column.value ? column.value(row) : getByPath(row, column.key);
}
