<template>
  <div class="dashboard-view">
    <div v-if="error" class="dashboard-alert">{{ error }}</div>

    <div class="responsive-kpi-grid">
      <StatCard label="Faturamento hoje" :value="money(summary.total_sold_today)" tone="success" caption="Pedidos pagos">
        <template #icon><AppIcon name="dollar-sign" :size="19" /></template>
      </StatCard>
      <StatCard label="Pedidos hoje" :value="String(summary.orders_count || 0)" tone="brand" :caption="`${summary.open_orders || 0} abertos`">
        <template #icon><AppIcon name="receipt-text" :size="19" /></template>
      </StatCard>
      <StatCard label="Ticket medio" :value="money(summary.average_ticket)" tone="info" caption="Media dos pagos">
        <template #icon><AppIcon name="trending-up" :size="19" /></template>
      </StatCard>
      <StatCard label="Itens na cozinha" :value="String(summary.kitchen_open_items || 0)" tone="warning" caption="Pendentes ou em preparo">
        <template #icon><AppIcon name="timer" :size="19" /></template>
      </StatCard>
    </div>

    <div class="responsive-two-col">
      <Card :title="'Faturamento'" :subtitle="chartSubtitle">
        <template #actions>
          <div class="tabs-sm">
            <SelectButton v-model="range" :options="rangeItems" option-label="label" option-value="value" :allow-empty="false" />
          </div>
        </template>

        <div class="dashboard-bars" :class="{ 'dashboard-bars--month': range === 'month' }">
          <div v-for="bar in bars" :key="bar.date" class="dashboard-bars__item">
            <div class="dashboard-bars__bar" :style="barStyle(bar)">
              <span v-if="bar.isMax && Number(bar.total || 0) > 0">{{ compactMoney(bar.total) }}</span>
            </div>
            <span>{{ bar.label }}</span>
          </div>
        </div>
      </Card>

      <Card title="Vendas por canal" :subtitle="channelSubtitle">
        <template #actions>
          <div class="tabs-sm">
            <SelectButton v-model="channelRange" :options="rangeItems" option-label="label" option-value="value" :allow-empty="false" />
          </div>
        </template>
        <div class="channels">
          <div v-for="channel in channels" :key="channel.label" class="channels__row">
            <div class="channels__meta">
              <span class="channels__label">
                <span :style="{ background: channel.color }" />{{ channel.label }}
              </span>
              <span class="num channels__value">{{ money(channel.total) }}</span>
            </div>
            <div class="channels__track">
              <div :style="{ width: `${channel.pct}%`, background: channel.color }" />
            </div>
          </div>
          <div v-if="!hasChannelSales" class="empty-state">Sem vendas pagas hoje.</div>
        </div>
      </Card>
    </div>

    <!-- Alertas de estoque baixo -->
    <Card v-if="stockAlerts.length" title="Alertas de estoque" :subtitle="`${stockAlerts.length} ingrediente(s) abaixo do minimo`" padding="none">
      <template #actions>
        <span class="stock-alert-badge">{{ stockAlerts.length }}</span>
      </template>
      <table class="orders-table">
        <thead>
          <tr>
            <th>Ingrediente</th>
            <th>Unidade</th>
            <th class="right">Saldo atual</th>
            <th class="right">Minimo</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="alert in stockAlerts" :key="alert.ingredient_id" class="stock-alert-row">
            <td class="semibold">{{ alert.ingredient_name }}</td>
            <td>{{ alert.unit }}</td>
            <td class="num right danger">{{ Number(alert.balance).toFixed(3) }}</td>
            <td class="num right muted">{{ Number(alert.minimum_stock).toFixed(3) }}</td>
          </tr>
        </tbody>
      </table>
    </Card>

    <Card title="Pedidos recentes" subtitle="Atualizacao em tempo real" padding="none">
      <template #actions>
        <Tag :severity="loading ? 'warning' : 'success'" :value="loading ? 'Atualizando' : 'Ao vivo'" />
      </template>

      <div class="orders-table-wrap">
        <table class="orders-table">
          <thead>
            <tr>
              <th v-for="(header, index) in headers" :key="header || index" :class="{ right: index >= 3 && index <= 4 }">
                {{ header }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in recentOrders" :key="order.id">
              <td class="num strong">#{{ order.sequence }}</td>
              <td class="semibold">{{ orderMainLabel(order) }}</td>
              <td><span class="muted">{{ orderType(order.order_type) }}</span></td>
              <td class="num right">{{ order.items?.length || 0 }}</td>
              <td class="num right strong">{{ money(order.total) }}</td>
              <td><Tag :severity="tagSeverity(order.status)" :value="orderStatus(order.status)" rounded /></td>
              <td class="num">{{ elapsed(order.opened_at) }}</td>
              <td class="right">
                <button class="orders-table__action" type="button" aria-label="Abrir pedido">
                  <AppIcon name="arrow-right" :size="15" />
                </button>
              </td>
            </tr>
            <tr v-if="!recentOrders.length && !loading">
              <td colspan="8" class="empty-row">Nenhum pedido encontrado.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

import SelectButton from "primevue/selectbutton";
import Tag from "primevue/tag";

import AppIcon from "../components/AppIcon.vue";
import Card from "../components/display/Card.vue";
import StatCard from "../components/data/StatCard.vue";
import { api } from "../services/api";

const loading = ref(false);
const error = ref("");
const summary = ref({});
const recentOrders = ref([]);
const chartOrders = ref([]);
const stockAlerts = ref([]);
const range = ref("week");
const channelRange = ref("day");
const headers = ["Pedido", "Tipo", "Canal", "Itens", "Total", "Status", "Tempo", ""];
const colors = ["var(--brand)", "var(--info)", "var(--success)", "var(--warning)", "var(--danger)"];
const defaultChannels = ["table", "delivery", "counter", "takeaway"];
const rangeItems = [
  { value: "day", label: "Dia" },
  { value: "week", label: "Semana" },
  { value: "month", label: "Mes" },
];

const chartSubtitle = computed(() => {
  const labels = { day: "por horario", week: "ultimos 7 dias", month: "dias do mes" };
  return `${money(chartTotal.value)} ${labels[range.value] || "no periodo"}`;
});

const channelSubtitle = computed(() => {
  const labels = { day: "hoje", week: "ultimos 7 dias", month: "este mes" };
  return labels[channelRange.value] || "hoje";
});

const chartRows = computed(() => {
  if (range.value === "day") {
    return chartSeries(summary.value.sales_today_by_hour, deriveHourlyRows, fallbackHourlyRows);
  }
  if (range.value === "month") {
    return chartSeries(summary.value.sales_current_month, deriveMonthRows, fallbackMonthRows);
  }
  return chartSeries(summary.value.sales_last_7_days, deriveDailyRows, fallbackDailyRows);
});

const chartTotal = computed(() => chartRows.value.reduce((total, row) => total + row.total, 0));

const bars = computed(() => {
  const rows = chartRows.value;
  const max = Math.max(...rows.map((row) => row.total), 0);
  return rows.map((row) => ({
    ...row,
    v: max ? Math.max(14, Math.round((row.total / max) * 100)) : 14,
    isMax: max > 0 && row.total === max,
  }));
});

const channels = computed(() => {
  const paid = paidOrdersForCharts();
  let rows;

  if (channelRange.value === "day") {
    const apiRows = Array.isArray(summary.value.sales_by_order_type) ? summary.value.sales_by_order_type : [];
    if (hasRowsWithSales(apiRows)) return buildChannels(apiRows);
    const today = dateKey(new Date());
    rows = aggregateByType(paid.filter((o) => dateKey(o.opened_at) === today));
  } else if (channelRange.value === "week") {
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 6);
    cutoff.setHours(0, 0, 0, 0);
    rows = aggregateByType(paid.filter((o) => new Date(o.opened_at) >= cutoff));
  } else {
    const now = new Date();
    rows = aggregateByType(paid.filter((o) => {
      const d = new Date(o.opened_at);
      return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
    }));
  }

  return buildChannels(rows);
});

const hasChannelSales = computed(() => channels.value.some((channel) => channel.total > 0));

async function loadDashboard() {
  loading.value = true;
  error.value = "";
  try {
    const [summaryResponse, ordersResponse, alertsResponse] = await Promise.all([
      api.get("/reports/dashboard/"),
      api.get("/orders/", { params: { ordering: "-opened_at", page_size: 50 } }),
      api.get("/stock/alerts/").catch(() => ({ data: { alerts: [] } })),
    ]);
    summary.value = summaryResponse.data || {};
    chartOrders.value = ordersResponse.data.results || ordersResponse.data || [];
    recentOrders.value = chartOrders.value.slice(0, 8);
    stockAlerts.value = alertsResponse.data?.alerts || [];
  } catch {
    error.value = "Nao foi possivel carregar os dados do painel.";
  } finally {
    loading.value = false;
  }
}

function chartSeries(apiRows, deriveRows, fallbackRows) {
  if (hasRowsWithSales(apiRows)) {
    return normalizeChartRows(apiRows, fallbackRows());
  }
  const derivedRows = deriveRows();
  if (hasRowsWithSales(derivedRows)) {
    return normalizeChartRows(derivedRows, fallbackRows());
  }
  return normalizeChartRows(apiRows, fallbackRows());
}

function normalizeChartRows(rows, fallbackRows) {
  const source = Array.isArray(rows) && rows.length ? rows : fallbackRows;
  return source.map((row, index) => ({
    date: row.date || row.label || String(index),
    label: chartLabel(row, index),
    total: toNumber(row.total),
  }));
}

function fallbackHourlyRows() {
  return ["08h", "10h", "12h", "14h", "16h", "18h", "20h", "22h"].map((label) => ({ label, total: 0 }));
}

function fallbackDailyRows() {
  return lastSevenDays().map((date) => ({ date, total: 0 }));
}

function fallbackMonthRows() {
  const today = new Date();
  const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
  return Array.from({ length: daysInMonth }, (_, index) => {
    const date = new Date(today.getFullYear(), today.getMonth(), index + 1);
    return { date: dateKey(date), label: String(index + 1).padStart(2, "0"), total: 0 };
  });
}

function deriveHourlyRows() {
  const buckets = fallbackHourlyRows().map((row, index) => ({
    ...row,
    start: 8 + index * 2,
    end: 10 + index * 2,
  }));
  paidOrdersForCharts()
    .filter((order) => dateKey(order.opened_at) === dateKey(new Date()))
    .forEach((order) => {
      const hour = new Date(order.opened_at).getHours();
      const bucket = buckets.find((row) => hour >= row.start && hour < row.end);
      if (bucket) bucket.total += toNumber(order.total);
    });
  return buckets.map(({ start, end, ...row }) => row);
}

function deriveDailyRows() {
  const rows = fallbackDailyRows();
  const totalsByDate = Object.fromEntries(rows.map((row) => [row.date, 0]));
  paidOrdersForCharts().forEach((order) => {
    const key = dateKey(order.opened_at);
    if (key in totalsByDate) totalsByDate[key] += toNumber(order.total);
  });
  return rows.map((row) => ({ ...row, total: totalsByDate[row.date] || 0 }));
}

function deriveMonthRows() {
  const rows = fallbackMonthRows();
  const totalsByDate = Object.fromEntries(rows.map((row) => [row.date, 0]));
  paidOrdersForCharts().forEach((order) => {
    const key = dateKey(order.opened_at);
    if (key in totalsByDate) totalsByDate[key] += toNumber(order.total);
  });
  return rows.map((row) => ({ ...row, total: totalsByDate[row.date] || 0 }));
}

function aggregateByType(orders) {
  const totals = {};
  orders.forEach((o) => {
    totals[o.order_type] = (totals[o.order_type] || 0) + toNumber(o.total);
  });
  return Object.entries(totals).map(([order_type, total]) => ({ order_type, total }));
}

function buildChannels(rows) {
  const rowByType = rows.reduce((acc, row) => {
    acc[row.order_type] = toNumber(row.total);
    return acc;
  }, {});
  const normalizedRows = [
    ...defaultChannels.map((t) => ({ order_type: t, total: rowByType[t] || 0 })),
    ...rows.filter((r) => !defaultChannels.includes(r.order_type)),
  ].map((r) => ({ ...r, total: toNumber(r.total) }));
  const max = Math.max(...normalizedRows.map((r) => r.total), 0);
  return normalizedRows.map((r, i) => ({
    label: orderType(r.order_type),
    total: r.total,
    pct: max && r.total > 0 ? Math.max(8, Math.round((r.total / max) * 100)) : 0,
    color: colors[i % colors.length],
  }));
}

function paidOrdersForCharts() {
  return chartOrders.value.filter((order) => order.payment_status === "paid" || order.status === "paid");
}

function hasRowsWithSales(rows) {
  return Array.isArray(rows) && rows.some((row) => toNumber(row.total) > 0);
}

function lastSevenDays() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() - (6 - index));
    return dateKey(date);
  });
}

function dateKey(value) {
  const date = value instanceof Date ? value : new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function chartLabel(row, index) {
  if (range.value === "day") return row.label || String(index + 1);
  if (range.value === "month") return row.label || row.date || String(index + 1);
  if (row.date) return dayLabel(row.date);
  return row.label || String(index + 1);
}

function dayLabel(date) {
  return new Date(`${date}T00:00:00`).toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
}

function toNumber(value) {
  if (typeof value === "number") return value;
  if (value == null || value === "") return 0;
  return Number(String(value).replace(",", ".")) || 0;
}

function barStyle(bar) {
  return {
    height: `${Math.max(0, Math.min(bar.v || 0, 100))}%`,
    background: bar.isMax ? "var(--brand)" : "var(--brand-subtle-2)",
  };
}

function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function compactMoney(value) {
  return Number(value || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    notation: "compact",
    maximumFractionDigits: 0,
  });
}

function orderMainLabel(order) {
  if (order.table_number) return `Mesa ${order.table_number}`;
  if (order.customer_name) return order.customer_name;
  return order.general_notes || orderType(order.order_type);
}

function orderType(value) {
  const labels = {
    table: "Salao",
    command: "Comanda",
    counter: "Balcao",
    delivery: "Delivery",
    takeaway: "Retirada",
    internal: "Interno",
  };
  return labels[value] || value || "-";
}

function orderStatus(value) {
  const labels = {
    open: "Aberto",
    sent_to_kitchen: "Cozinha",
    preparing: "Preparo",
    partially_ready: "Parcial",
    ready: "Pronto",
    delivered: "Entregue",
    awaiting_payment: "Pagamento",
    paid: "Pago",
    cancelled: "Cancelado",
    refunded: "Estornado",
  };
  return labels[value] || value || "-";
}

function tagSeverity(value) {
  if (["paid", "delivered", "ready"].includes(value)) return "success";
  if (["cancelled", "refunded"].includes(value)) return "danger";
  if (["preparing", "sent_to_kitchen", "awaiting_payment"].includes(value)) return "warning";
  return "info";
}

function elapsed(value) {
  if (!value) return "-";
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

onMounted(loadDashboard);
</script>

<style scoped>
.dashboard-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.dashboard-alert {
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--danger-subtle);
  color: var(--danger-text);
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
}

.dashboard-bars {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  height: 200px;
  padding-top: 34px;
}

.dashboard-bars--month {
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 4px;
}

.dashboard-bars__item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  height: 100%;
  justify-content: flex-end;
}

.dashboard-bars--month .dashboard-bars__item {
  flex: 0 0 28px;
}

.dashboard-bars__bar {
  width: 100%;
  max-width: 38px;
  border-radius: var(--radius-sm) var(--radius-sm) 3px 3px;
  position: relative;
  transition: height var(--dur-slow) var(--ease-out);
}

.dashboard-bars__bar span {
  position: absolute;
  top: -28px;
  left: 50%;
  transform: translateX(-50%);
  max-width: 64px;
  padding: 3px 6px;
  border-radius: var(--radius-pill);
  background: var(--surface-card);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xs);
  font: var(--weight-bold) 10px/1 var(--font-mono);
  color: var(--text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dashboard-bars__item > span {
  font: var(--weight-semibold) 11px/1 var(--font-sans);
  color: var(--text-muted);
}

.channels {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.channels__row {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.channels__meta {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.channels__label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: var(--weight-semibold) 13px/1 var(--font-sans);
  color: var(--text-body);
}

.channels__label span {
  width: 9px;
  height: 9px;
  border-radius: 3px;
}

.channels__value {
  font: var(--weight-bold) 13px/1 var(--font-mono);
  color: var(--text-strong);
}

.channels__track {
  height: 7px;
  border-radius: 999px;
  background: var(--surface-sunken);
  overflow: hidden;
}

.channels__track div {
  height: 100%;
  border-radius: 999px;
}

.empty-state,
.empty-row {
  color: var(--text-muted);
  font: var(--weight-medium) 13px/1.5 var(--font-sans);
  text-align: center;
}

.stock-alert-badge {
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  background: #fee2e2;
  color: #991b1b;
  font: var(--weight-bold) 11.5px/1 var(--font-mono);
}

.stock-alert-row {
  background: rgba(254, 226, 226, 0.15);
}

.danger {
  color: #dc2626;
  font-weight: var(--weight-bold);
}

.orders-table-wrap {
  overflow-x: auto;
}

.orders-table {
  width: 100%;
  border-collapse: collapse;
}

.orders-table th {
  text-align: left;
  padding: 12px 18px;
  font: var(--weight-bold) 11px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--text-subtle);
  border-bottom: 1px solid var(--border);
  background: var(--surface-sunken);
  white-space: nowrap;
}

.orders-table td {
  padding: 13px 18px;
  white-space: nowrap;
  border-bottom: 1px solid var(--border-subtle);
  font: var(--weight-medium) 13px/1 var(--font-sans);
  color: var(--text-body);
}

.orders-table .right {
  text-align: right;
}

.orders-table .strong {
  font-weight: var(--weight-bold);
  color: var(--text-strong);
}

.orders-table .semibold {
  font-weight: var(--weight-semibold);
}

.orders-table .muted {
  font: var(--weight-medium) 12.5px/1 var(--font-sans);
  color: var(--text-muted);
}

.orders-table__action {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.tabs-sm :deep(.p-selectbutton .p-button) {
  height: 26px;
  padding: 0 10px;
  font-size: 12px;
}

:deep(.p-tag) {
  border: 1px solid transparent;
  font: var(--weight-extra) 11px/1 var(--font-sans);
}

:deep(.p-tag.p-tag-info) {
  background: #1d4ed8;
  border-color: #1e40af;
  color: #fff;
}

:deep(.p-tag.p-tag-success) {
  background: #047857;
  border-color: #065f46;
  color: #fff;
}

:deep(.p-tag.p-tag-warning) {
  background: #b45309;
  border-color: #92400e;
  color: #fff;
}

:deep(.p-tag.p-tag-danger) {
  background: #b91c1c;
  border-color: #991b1b;
  color: #fff;
}

:deep(.p-tag.p-tag-secondary) {
  background: #475569;
  border-color: #334155;
  color: #fff;
}
</style>
