/**
 * O aviso no fim de uma ação em massa de pedidos: quantos foram e, se algum
 * ficou de fora, quais e por quê — sem isso o operador via "3 de 5" e não
 * sabia o que fazer com os dois que sobraram.
 */
export function resumoDoLote(feitos, verbo, pulados = []) {
  const detalhe = pulados.length
    ? `${pulados.length} ${pulados.length === 1 ? "ficou" : "ficaram"} de fora: ${pulados
      .slice(0, 3)
      .map((p) => `#${p.sequence} (${p.reason})`)
      .join("; ")}${pulados.length > 3 ? "…" : ""}`
    : undefined;
  return {
    severity: pulados.length ? "warn" : "success",
    summary: `${feitos || 0} pedido(s) ${verbo}`,
    detail: detalhe,
    life: pulados.length ? 9000 : 4000,
  };
}
