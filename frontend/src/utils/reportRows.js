export function waiterRowsFrom(report) {
  return (report.by_waiter || []).map((row) => {
    const operatorCode = row.operator_code || "";
    return {
      name: operatorCode ? `Garçom · ${operatorCode}` : row.operator_name || "Não identificado",
      username: row.operator_username || "-",
      operator_code: operatorCode || "Não informado",
      count: row.count,
      items: row.items,
      total: row.total,
    };
  });
}

export function productRowsFrom(report) {
  return (report.by_product || []).map((row) => ({
    id: row.product__id,
    name: row.product__name || "Produto removido",
    quantity: row.quantity,
    total: row.total,
    average_unit_price: row.average_unit_price,
  }));
}

export function productSalesRoute(row, { dateFrom, dateTo, restaurantId }) {
  if (!row.id) return null;
  return {
    name: "relatorio-produto-detalhe",
    params: { productId: row.id },
    query: {
      date_from: dateFrom,
      date_to: dateTo,
      ...(restaurantId ? { restaurant: restaurantId } : {}),
    },
  };
}
