/**
 * O aviso no fim do zeramento: quantas comandas voltaram livres e, se alguma
 * ficou, qual e por quê. "3 de 5" sem o motivo deixava o operador sem saber
 * que a comanda 14 estava numa conta aberta e a 22 precisava da senha.
 */
export function resumoDoZeramento(zeradas = [], puladas = []) {
  const itens = zeradas.reduce((total, comanda) => total + (comanda.items_removed || 0), 0);
  const detalhe = puladas.length
    ? `${puladas.length} ${puladas.length === 1 ? "ficou" : "ficaram"} como estava: ${puladas
      .slice(0, 3)
      .map((p) => `${p.number ? `comanda ${p.number}` : "comanda"} (${p.reason})`)
      .join("; ")}${puladas.length > 3 ? "…" : ""}`
    : undefined;
  return {
    severity: puladas.length ? "warn" : "success",
    summary: `${zeradas.length} comanda(s) zerada(s), ${itens} item(ns) retirado(s)`,
    detail: detalhe,
    life: puladas.length ? 9000 : 4000,
  };
}
