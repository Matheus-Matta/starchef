import { api } from "./api";

export const endpoints = {
  sales: "/reports/sales/",
  cash: "/reports/cash-movements/",
  orders: "/reports/orders/",
  product: "/reports/products/",
  payment: "/reports/payments/",
  waiter: "/reports/waiters/",
  restaurant: "/reports/restaurants/",
  coupon: "/reports/coupons/",
  command: "/reports/commands/",
  cost: "/reports/product-costs/",
};

/**
 * Linhas por lista de relatório: TODAS, até este teto (o do servidor).
 *
 * A tabela do relatório ordena e pagina no navegador. Pedindo 10 linhas, a
 * seção mostrava 10 e a tabela achava que eram todas: ordenar "do maior para
 * o menor" escolhia o maior entre as 10. Passando do teto, a tabela avisa
 * (`ReportDataTable`, `total`).
 */
export const LINHAS_DO_RELATORIO = 1000;
export const REPORT_CACHE_TTL_MS = 15_000;

export const reportService = {
  async get(section, filters = {}, { forceRefresh = false } = {}) {
    const response = await api.get(endpoints[section] || endpoints.sales, {
      params: { page: 1, page_size: LINHAS_DO_RELATORIO, ...filters },
      cacheTtlMs: REPORT_CACHE_TTL_MS,
      forceRefresh,
    });
    return response.data || {};
  },
  async getCouponRedemptions(couponId, filters = {}) {
    const response = await api.get(endpoints.coupon, { params: { ...filters, coupon: couponId } });
    return response.data || {};
  },
  async getProductSales(productId, filters = {}) {
    const response = await api.get(`/reports/products/${productId}/sales/`, { params: filters });
    return response.data || {};
  },
};
