import { api } from "./api";

const endpoints = {
  sales: "/reports/sales/",
  orders: "/reports/orders/",
  product: "/reports/products/",
  payment: "/reports/payments/",
  waiter: "/reports/waiters/",
  restaurant: "/reports/restaurants/",
};

export const reportService = {
  async get(section, filters = {}) {
    const response = await api.get(endpoints[section] || endpoints.sales, {
      // O DataTable pagina de 10 em 10 no cliente. Para produtos, carregamos o
      // conjunto consolidado para que ordenar por quantidade não considere
      // apenas os 10 primeiros por faturamento.
      params: { page: 1, page_size: section === "product" ? 100 : 10, ...filters },
    });
    return response.data || {};
  },
};
