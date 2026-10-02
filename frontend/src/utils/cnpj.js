/**
 * CNPJ para a NFC-e: caracteres úteis, máscara e dígito verificador.
 *
 * Aceita o CNPJ alfanumérico da Receita (letras nas 12 primeiras posições; os
 * dois verificadores continuam números). A conta é a mesma do backend
 * (`customers/validators.py`) e do PDV desktop: cada caractere vale o código
 * dele menos 48, então os dígitos valem o que sempre valeram.
 */
export function cnpjDigits(value) {
  return String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 14);
}

export function formatCnpj(value) {
  return cnpjDigits(value)
    .replace(/^(\w{2})(\w)/, "$1.$2")
    .replace(/^(\w{2})\.(\w{3})(\w)/, "$1.$2.$3")
    .replace(/\.(\w{3})(\w)/, ".$1/$2")
    .replace(/(\w{4})(\w{1,2})$/, "$1-$2");
}

export function isValidCnpj(value) {
  const cnpj = cnpjDigits(value);
  if (cnpj.length !== 14 || /^(\w)\1{13}$/.test(cnpj) || !/^\d{2}$/.test(cnpj.slice(12))) return false;
  const digito = (base) => {
    const pesos = base.length === 12 ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    const soma = base.split("").reduce((total, c, i) => total + (c.charCodeAt(0) - 48) * pesos[i], 0);
    const resto = soma % 11;
    return resto < 2 ? 0 : 11 - resto;
  };
  const primeiro = digito(cnpj.slice(0, 12));
  const segundo = digito(cnpj.slice(0, 12) + primeiro);
  return Number(cnpj[12]) === primeiro && Number(cnpj[13]) === segundo;
}
