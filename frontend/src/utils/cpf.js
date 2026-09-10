export function cpfDigits(value) {
  return String(value || "").replace(/\D/g, "").slice(0, 11);
}

export function formatCpf(value) {
  const digits = cpfDigits(value);
  return digits
    .replace(/^(\d{3})(\d)/, "$1.$2")
    .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
}

export function isValidCpf(value) {
  const cpf = cpfDigits(value);
  if (cpf.length !== 11 || /^(\d)\1{10}$/.test(cpf)) return false;

  for (let length = 9; length <= 10; length += 1) {
    const sum = cpf
      .slice(0, length)
      .split("")
      .reduce((total, digit, index) => total + Number(digit) * (length + 1 - index), 0);
    const remainder = (sum * 10) % 11;
    const expected = remainder === 10 ? 0 : remainder;
    if (Number(cpf[length]) !== expected) return false;
  }
  return true;
}
