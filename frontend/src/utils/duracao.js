/**
 * Minutos como o gerente lê: "1 h 25 min", "45 min".
 *
 * `null` é "não houve" (nenhuma comanda paga no período) e vira "—", não
 * "0 min": zero minutos diria que as comandas foram pagas na hora.
 */
export function duracao(minutos) {
  if (minutos == null) return "—";
  if (minutos < 1) return "menos de 1 min";
  const total = Math.round(minutos);
  const horas = Math.floor(total / 60);
  const resto = total % 60;
  if (!horas) return `${resto} min`;
  return resto ? `${horas} h ${resto} min` : `${horas} h`;
}
