/**
 * Conversao de unidades no navegador — espelho de `apps/menu/units.py`.
 *
 * Serve so para a PREVIA que a tela mostra enquanto o operador digita ("isto
 * vai somar 10.000 g ao saldo"). O calculo que vale e o do backend; duplicar a
 * tabela aqui evita um ida-e-volta a cada tecla, e o teste garante que as duas
 * listas nao se desencontrem.
 *
 * Grandezas diferentes devolvem `null` em vez de um numero: litro para grama
 * depende da densidade, e um fator generico daria um valor plausivel e errado.
 */
const WEIGHT = "weight";
const VOLUME = "volume";
const COUNT = "count";

const UNITS = {
  kg: { dimension: WEIGHT, factor: 1000 },
  g: { dimension: WEIGHT, factor: 1 },
  l: { dimension: VOLUME, factor: 1000 },
  ml: { dimension: VOLUME, factor: 1 },
  unit: { dimension: COUNT, factor: 1 },
};

export function dimensionOf(unit) {
  return UNITS[unit]?.dimension ?? null;
}

/** `quantity` de `fromUnit` expressa em `toUnit`, ou `null` se incompativel. */
export function convertUnit(quantity, fromUnit, toUnit) {
  // `Number(null)` e `Number("")` valem 0, nao NaN — sem esta guarda um campo
  // vazio viraria "0 g" na previa, que parece um valor calculado quando na
  // verdade o operador ainda nao digitou nada.
  if (quantity === null || quantity === undefined || quantity === "") return null;
  const amount = Number(quantity);
  if (!Number.isFinite(amount)) return null;
  if (fromUnit === toUnit) return amount;

  const from = UNITS[fromUnit];
  const to = UNITS[toUnit];
  if (!from || !to || from.dimension !== to.dimension) return null;

  return (amount * from.factor) / to.factor;
}
