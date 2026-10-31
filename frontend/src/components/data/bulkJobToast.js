export function bulkJobToast(data, label) {
  const total = Number(data?.total || 0);
  return {
    severity: "info",
    summary: "Processamento iniciado",
    detail: data?.message || `${total} ${label} recebido(s). Aguarde; o resultado aparecerá no sino de notificações.`,
    life: 7000,
  };
}
