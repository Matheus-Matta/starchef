/**
 * Como uma célula de relatório aparece.
 *
 * Sem tipo na coluna o valor saía cru do banco — uma soma de DecimalField
 * chega como "10.00000000000000". Número com casas decimais passa a ter no
 * máximo 2; `digits` na coluna pede mais (peso em kg, por exemplo).
 */
const DECIMAL = /^-?\d+\.\d+$/;

function decimal(value, digits = 2) {
  return Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: digits });
}

export function formatReportCell(value, column = {}) {
  if (column.type === "money") {
    return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  if (column.type === "decimal") return decimal(value, column.digits ?? 2);
  if (value == null || value === "") return "—";
  if ((typeof value === "number" && !Number.isInteger(value)) || (typeof value === "string" && DECIMAL.test(value))) {
    return decimal(value, column.digits ?? 2);
  }
  return value;
}
