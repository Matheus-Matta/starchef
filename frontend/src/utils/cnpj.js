/** CNPJ para a NFC-e: só dígitos, máscara e dígito verificador. */
export function cnpjDigits(value) {
  return String(value || "").replace(/\D/g, "").slice(0, 14);
}

export function formatCnpj(value) {
  return cnpjDigits(value)
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
}

export function isValidCnpj(value) {
  const cnpj = cnpjDigits(value);
  if (cnpj.length !== 14 || /^(\d)\1{13}$/.test(cnpj)) return false;
  const digito = (base) => {
    const pesos = base.length === 12 ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    const soma = base.split("").reduce((total, d, i) => total + Number(d) * pesos[i], 0);
    const resto = soma % 11;
    return resto < 2 ? 0 : 11 - resto;
  };
  const primeiro = digito(cnpj.slice(0, 12));
  const segundo = digito(cnpj.slice(0, 12) + primeiro);
  return Number(cnpj[12]) === primeiro && Number(cnpj[13]) === segundo;
}
