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
};

export const reportService = {
  async get(section, filters = {}) {
    const response = await api.get(endpoints[section] || endpoints.sales, {
      // O DataTable pagina de 10 em 10 no cliente. Para produtos, carregamos o
      // conjunto consolidado para que ordenar por quantidade não considere
      // apenas os 10 primeiros por faturamento.
      params: {
        page: 1,
        page_size: ["product", "waiter", "sales"].includes(section) ? 100 : 10,
        ...filters,
      },
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
