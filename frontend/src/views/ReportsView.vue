<template>
  <div class="reports-view">
    <div class="reports-view__filters">
      <div class="reports-view__restaurant-filter">
        <select v-model="selectedRestaurantId" aria-label="Restaurante" :disabled="loadingRestaurants" @change="handleRestaurantChange">
          <option value="">Todos os restaurantes</option>
          <option v-for="restaurant in restaurants" :key="restaurant.id" :value="restaurant.id">
            {{ restaurant.trade_name || restaurant.legal_name || restaurant.name }}
          </option>
        </select>
      </div>
      <template v-if="section === 'product'">
        <select v-model="productFilters.category" class="reports-view__select" aria-label="Categoria" @change="loadReport">
          <option value="">Todas as categorias</option>
          <option v-for="category in categories" :key="category.id" :value="category.id">{{ category.name }}</option>
        </select>
        <select v-model="productFilters.sector" class="reports-view__select" aria-label="Setor" @change="loadReport">
          <option value="">Todos os setores</option>
          <option v-for="sector in sectors" :key="sector.id" :value="sector.id">{{ sector.name }}</option>
        </select>
        <select v-model="productFilters.product_type" class="reports-view__select" aria-label="Tipo de produto" @change="loadReport">
          <option value="">Todos os tipos</option>
          <option value="meal">Refeição</option>
          <option value="drink">Bebida</option>
          <option value="dessert">Sobremesa</option>
          <option value="combo">Combo</option>
          <option value="addon">Adicional</option>
          <option value="input">Insumo</option>
        </select>
        <select v-model="productFilters.production_sector" class="reports-view__select" aria-label="Setor de produção" @change="loadReport">
          <option value="">Toda a produção</option>
          <option value="kitchen">Cozinha</option>
          <option value="bar">Bar</option>
          <option value="dessert">Sobremesas</option>
        </select>
      </template>
      <AppDateRange
        v-model="reportPeriod"
        class="reports-view__range"
        placeholder="Período do relatório"
        @change="loadReport"
      />
      <button class="reports-view__button" type="button" :disabled="loading" @click="loadReport">
        {{ loading ? "Carregando..." : "Atualizar" }}
      </button>
      <button class="reports-view__button reports-view__button--outline" type="button" :disabled="loading" @click="exportCsv">
        <AppIcon name="download" :size="14" /> Exportar CSV
      </button>
    </div>

    <div v-if="section === 'sales'" class="responsive-kpi-grid">
      <StatCard label="Total vendido" :value="money(report.total)" tone="success" caption="Periodo selecionado">
        <template #icon><AppIcon name="dollar-sign" :size="19" /></template>
      </StatCard>
      <StatCard label="Pedidos pagos" :value="String(report.orders || 0)" tone="brand" caption="Periodo selecionado">
        <template #icon><AppIcon name="receipt-text" :size="19" /></template>
      </StatCard>
      <StatCard label="Ticket medio" :value="money(ticketMedio)" tone="neutral" caption="Por pedido pago">
        <template #icon><AppIcon name="trending-up" :size="19" /></template>
      </StatCard>
      <StatCard label="Itens vendidos" :value="String(totalItems)" tone="neutral" caption="Total de unidades">
        <template #icon><AppIcon name="package" :size="19" /></template>
      </StatCard>
    </div>

    <div v-if="section === 'orders'" class="responsive-kpi-grid">
      <StatCard label="Pedidos no período" :value="String(report.orders_total || 0)" tone="brand" caption="Todos os status" />
      <StatCard label="Pedidos pagos" :value="String(report.orders || 0)" tone="success" :caption="money(report.total)" />
      <StatCard label="Pedidos abertos" :value="String(report.orders_open || 0)" tone="warning" caption="Aguardando conclusão" />
      <StatCard label="Cancelados" :value="String(report.orders_cancelled || 0)" tone="danger" caption="No período selecionado" />
    </div>

    <div v-if="section === 'product'" class="responsive-kpi-grid">
      <StatCard label="Itens vendidos" :value="decimal(report.items_quantity)" tone="brand" caption="Sem cancelamentos e cortesias" />
      <StatCard label="Receita dos itens" :value="money(report.items_total)" tone="success" caption="Produtos pagos" />
      <StatCard label="Produtos diferentes" :value="String(productRows.length)" tone="neutral" caption="Com venda no período" />
      <StatCard label="Média por item" :value="money(averageItemValue)" tone="info" caption="Receita por unidade" />
    </div>

    <div v-if="section === 'payment'" class="responsive-kpi-grid">
      <StatCard label="Total recebido" :value="money(report.payments_total)" tone="success" caption="Pagamentos aprovados" />
      <StatCard label="Transações" :value="String(report.payments_count || 0)" tone="brand" caption="No período selecionado" />
      <StatCard label="Ticket médio" :value="money(paymentAverage)" tone="info" caption="Por transação" />
      <StatCard label="Estornado" :value="money(report.payments_refunded?.total)" tone="danger" :caption="`${report.payments_refunded?.count || 0} transações`" />
    </div>

    <div v-if="section === 'waiter'" class="responsive-kpi-grid">
      <StatCard label="Vendas da equipe" :value="money(report.total)" tone="success" caption="Pedidos pagos" />
      <StatCard label="Atendentes com venda" :value="String(waiterRows.length)" tone="brand" caption="No período selecionado" />
      <StatCard label="Pedidos atendidos" :value="String(report.orders || 0)" tone="neutral" caption="Total pago" />
      <StatCard label="Ticket médio" :value="money(report.average_ticket)" tone="info" caption="Por pedido" />
    </div>

    <div v-if="section === 'restaurant'" class="responsive-kpi-grid">
      <StatCard label="Faturamento consolidado" :value="money(report.total)" tone="success" caption="Todos os restaurantes no escopo" />
      <StatCard label="Restaurantes com venda" :value="String(restaurantRows.length)" tone="brand" caption="No período selecionado" />
      <StatCard label="Pedidos pagos" :value="String(report.orders || 0)" tone="neutral" caption="Total consolidado" />
      <StatCard label="Ticket médio" :value="money(report.average_ticket)" tone="info" caption="Por pedido" />
    </div>

    <div v-if="section === 'sales'" class="reports-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="reports-tab"
        :class="{ 'reports-tab--active': activeTab === tab.id }"
        type="button"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <div v-if="section === 'sales' && activeTab === 'payment'" class="responsive-two-col">
      <Card title="Distribuição dos recebimentos">
        <div class="report-chart"><Chart type="doughnut" :data="paymentChartData" :options="doughnutOptions" /></div>
      </Card>
      <Card title="Faturamento por restaurante">
        <div class="report-chart"><Chart type="bar" :data="restaurantChartData" :options="barOptions" /></div>
      </Card>
    </div>

    <div v-if="section === 'sales' && activeTab === 'payment'" class="responsive-two-col">
      <Card title="Por forma de pagamento" padding="none">
        <ReportDataTable :rows="paymentRows" :columns="paymentColumns" />
      </Card>
      <Card title="Por restaurante" padding="none">
        <ReportDataTable :rows="restaurantRows" :columns="restaurantColumns" />
      </Card>
    </div>

    <div v-if="section === 'waiter' || (section === 'sales' && activeTab === 'waiter')" class="responsive-one-col">
      <Card title="Ranking de vendas por garçom">
        <div class="report-chart report-chart--wide"><Chart type="bar" :data="waiterChartData" :options="barOptions" /></div>
      </Card>
      <Card title="Vendas por garcom" padding="none">
        <ReportDataTable :rows="waiterRows" :columns="waiterColumns" />
      </Card>
    </div>

    <div v-if="section === 'product' || (section === 'sales' && activeTab === 'product')" class="responsive-one-col">
      <Card title="Produtos com maior faturamento">
        <div class="report-chart report-chart--wide"><Chart type="bar" :data="productChartData" :options="barOptions" /></div>
      </Card>
      <Card title="Vendas por produto" padding="none">
        <ReportDataTable :rows="productRows" :columns="productColumns" />
      </Card>
    </div>

    <div v-if="section === 'payment'" class="responsive-one-col">
      <Card title="Participação por forma de pagamento">
        <div class="report-chart"><Chart type="doughnut" :data="paymentChartData" :options="doughnutOptions" /></div>
      </Card>
      <Card title="Recebimentos por forma de pagamento" padding="none">
        <ReportDataTable :rows="paymentRows" :columns="paymentColumns" />
      </Card>
    </div>

    <div v-if="section === 'restaurant'" class="responsive-one-col">
      <Card title="Comparativo de faturamento por restaurante">
        <div class="report-chart report-chart--wide"><Chart type="bar" :data="restaurantChartData" :options="barOptions" /></div>
      </Card>
      <Card title="Vendas por restaurante" padding="none">
        <ReportDataTable :rows="restaurantRows" :columns="restaurantColumns" />
      </Card>
    </div>

    <div v-if="section === 'orders'" class="responsive-two-col">
      <Card title="Distribuição por status">
        <div class="report-chart"><Chart type="doughnut" :data="orderStatusChartData" :options="doughnutOptions" /></div>
      </Card>
      <Card title="Pedidos por tipo">
        <div class="report-chart"><Chart type="bar" :data="orderTypeChartData" :options="barOptions" /></div>
      </Card>
    </div>

    <div v-if="section === 'orders'" class="responsive-two-col">
      <Card title="Pedidos por status" padding="none">
        <ReportDataTable :rows="orderStatusRows" :columns="orderBreakdownColumns" />
      </Card>
      <Card title="Pedidos por tipo" padding="none">
        <ReportDataTable :rows="orderTypeRows" :columns="orderBreakdownColumns" />
      </Card>
    </div>

    <div v-if="section === 'orders'" class="responsive-one-col">
      <Card title="Ocorrências por motivo">
        <div class="report-chart report-chart--wide"><Chart type="bar" :data="cancellationChartData" :options="barOptions" /></div>
      </Card>
      <Card title="Motivos de desistência e cancelamento" subtitle="Pedidos, itens removidos e cortesias no período" padding="none">
        <ReportDataTable :rows="cancellationReasonRows" :columns="cancellationReasonColumns" />
      </Card>
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from "vue";
import Chart from "primevue/chart";

import AppIcon from "../components/AppIcon.vue";
import StatCard from "../components/data/StatCard.vue";
import Card from "../components/display/Card.vue";
import AppDateRange from "../components/form/AppDateRange.vue";
import ReportDataTable from "../components/data/ReportDataTable.vue";
import { api, API_BASE_URL } from "../services/api";
import { reportService } from "../services/reportService";
import { useRealtimeResource } from "../composables/useRealtimeResource";
import { currentMonthRange } from "../utils/dateRange";

const props = defineProps({
  section: { type: String, default: "sales" },
});
useRealtimeResource(
  ["orders.order", "orders.orderitem", "payments.payment"],
  () => loadReport(),
  { debounce: 300 },
);

const today = new Date();
const reportPeriod = ref(currentMonthRange(today));
const theme = inject("theme");
const dateFrom = computed(() => ymd(reportPeriod.value?.[0] || today));
const dateTo = computed(() => ymd(reportPeriod.value?.[1] || reportPeriod.value?.[0] || today));
const report = ref({});
const loading = ref(false);
const loadingRestaurants = ref(false);
const restaurants = ref([]);
const categories = ref([]);
const sectors = ref([]);
const productFilters = reactive({
  category: "",
  sector: "",
  product_type: "",
  production_sector: "",
});
const selectedRestaurantId = ref(localStorage.getItem("starchef-restaurant-scope") || "");
const activeTab = ref("payment");

const tabs = [
  { id: "payment", label: "Por pagamento e restaurante" },
  { id: "waiter", label: "Por garcom" },
  { id: "product", label: "Por produto" },
];

const ticketMedio = computed(() => {
  if (!report.value.orders) return 0;
  return (report.value.total || 0) / report.value.orders;
});

const totalItems = computed(() =>
  (report.value.by_product || []).reduce((sum, row) => sum + Number(row.quantity || 0), 0),
);
const averageItemValue = computed(() =>
  Number(report.value.items_quantity || 0)
    ? Number(report.value.items_total || 0) / Number(report.value.items_quantity)
    : 0,
);
const paymentAverage = computed(() =>
  Number(report.value.payments_count || 0)
    ? Number(report.value.payments_total || 0) / Number(report.value.payments_count)
    : 0,
);

const paymentColumns = [
  { key: "name", label: "Forma" },
  { key: "count", label: "Pagamentos" },
  { key: "total", label: "Total", align: "right", type: "money" },
];
const restaurantColumns = [
  { key: "name", label: "Restaurante" },
  { key: "count", label: "Pedidos" },
  { key: "total", label: "Total", align: "right", type: "money" },
  { key: "average_ticket", label: "Ticket médio", align: "right", type: "money" },
];
const orderBreakdownColumns = [
  { key: "name", label: "Categoria" },
  { key: "count", label: "Pedidos", align: "right" },
  { key: "total", label: "Valor", align: "right", type: "money" },
];
const cancellationReasonColumns = [
  { key: "kind", label: "Origem" },
  { key: "reason", label: "Motivo" },
  { key: "count", label: "Ocorrências", align: "right" },
  { key: "value", label: "Valor impactado", align: "right", type: "money" },
];
const waiterColumns = [
  { key: "name", label: "Garcom" },
  { key: "username", label: "Usuario" },
  { key: "count", label: "Pedidos" },
  { key: "total", label: "Total", align: "right", type: "money" },
];
const productColumns = [
  { key: "name", label: "Produto" },
  { key: "quantity", label: "Qtd. vendida", align: "right" },
  { key: "average_unit_price", label: "Preço médio", align: "right", type: "money" },
  { key: "total", label: "Total", align: "right", type: "money" },
];

const paymentRows = computed(() =>
  (report.value.by_payment_method || []).map((row) => ({
    name: row.payment_method__name || row.payments__payment_method__name || "Não informado",
    count: row.count,
    total: row.total,
  })),
);
const restaurantRows = computed(() =>
  (report.value.by_restaurant || []).map((row) => ({
    name: row.restaurant__trade_name || "Restaurante não informado",
    count: row.count,
    total: row.total,
    average_ticket: row.average_ticket,
  })),
);
const waiterRows = computed(() =>
  (report.value.by_waiter || []).map((row) => {
    const first = row.responsible_user__first_name || "";
    const last = row.responsible_user__last_name || "";
    const fullName = `${first} ${last}`.trim() || "Nao identificado";
    return {
      name: fullName,
      username: row.responsible_user__username || "-",
      count: row.count,
      total: row.total,
    };
  }),
);
const productRows = computed(() =>
  (report.value.by_product || []).map((row) => ({
    name: row.product__name || "Produto removido",
    quantity: row.quantity,
    total: row.total,
    average_unit_price: row.average_unit_price,
  })),
);
const orderStatusLabels = {
  open: "Aberto",
  awaiting_payment: "Aguardando pagamento",
  paid: "Pago",
  cancelled: "Cancelado",
  refunded: "Estornado",
};
const orderTypeLabels = {
  table: "Mesa",
  command: "Comanda",
  counter: "Balcão",
  delivery: "Entrega",
  takeaway: "Retirada",
  internal: "Consumo interno",
};
const orderStatusRows = computed(() =>
  (report.value.by_status || []).map((row) => ({
    name: orderStatusLabels[row.status] || row.status,
    count: row.count,
    total: row.total,
  })),
);
const orderTypeRows = computed(() =>
  (report.value.by_order_type || []).map((row) => ({
    name: orderTypeLabels[row.order_type] || row.order_type,
    count: row.count,
    total: row.total,
  })),
);
const cancellationReasonRows = computed(() =>
  (report.value.by_cancellation_reason || []).map((row) => ({
    kind: row.kind,
    reason: row.reason,
    count: row.count,
    value: row.value,
  })),
);

const chartColors = ["#F97316", "#3B82F6", "#22C55E", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4", "#EC4899", "#84CC16", "#64748B"];
const chartTextColor = computed(() => theme?.value === "dark" ? "#E4E4E7" : "#433C32");
const chartGridColor = computed(() => theme?.value === "dark" ? "rgba(255,255,255,.08)" : "rgba(67,60,50,.10)");

function datasetFrom(rows, valueKey, label, color = chartColors[0]) {
  return {
    labels: rows.slice(0, 10).map((row) => row.name || row.reason || "Não informado"),
    datasets: [{
      label,
      data: rows.slice(0, 10).map((row) => Number(row[valueKey] || 0)),
      backgroundColor: color,
      borderRadius: 7,
      maxBarThickness: 42,
    }],
  };
}

function doughnutFrom(rows, valueKey, label) {
  return {
    labels: rows.slice(0, 10).map((row) => row.name || "Não informado"),
    datasets: [{
      label,
      data: rows.slice(0, 10).map((row) => Number(row[valueKey] || 0)),
      backgroundColor: chartColors,
      borderColor: theme?.value === "dark" ? "#18181B" : "#FFFFFF",
      borderWidth: 2,
      hoverOffset: 8,
    }],
  };
}

const paymentChartData = computed(() => doughnutFrom(paymentRows.value, "total", "Recebimentos"));
const restaurantChartData = computed(() => datasetFrom(restaurantRows.value, "total", "Faturamento", chartColors[1]));
const waiterChartData = computed(() => datasetFrom(waiterRows.value, "total", "Vendas", chartColors[2]));
const productChartData = computed(() => datasetFrom(productRows.value, "total", "Faturamento", chartColors[0]));
const orderStatusChartData = computed(() => doughnutFrom(orderStatusRows.value, "count", "Pedidos"));
const orderTypeChartData = computed(() => datasetFrom(orderTypeRows.value, "count", "Pedidos", chartColors[3]));
const cancellationChartData = computed(() => datasetFrom(cancellationReasonRows.value, "count", "Ocorrências", chartColors[4]));

const doughnutOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  cutout: "62%",
  plugins: {
    legend: {
      position: "bottom",
      labels: { color: chartTextColor.value, usePointStyle: true, padding: 16 },
    },
    tooltip: {
      callbacks: {
        label: (context) => `${context.label}: ${Number(context.raw || 0).toLocaleString("pt-BR")}`,
      },
    },
  },
}));

const barOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
  },
  scales: {
    x: {
      ticks: { color: chartTextColor.value, maxRotation: 35, minRotation: 0 },
      grid: { display: false },
      border: { color: chartGridColor.value },
    },
    y: {
      beginAtZero: true,
      ticks: { color: chartTextColor.value },
      grid: { color: chartGridColor.value },
      border: { display: false },
    },
  },
}));

async function loadReport() {
  loading.value = true;
  try {
    report.value = await reportService.get(props.section, {
      date_from: dateFrom.value,
      date_to: dateTo.value,
      restaurant: selectedRestaurantId.value,
      ...(props.section === "product" ? productFilters : {}),
    });
  } finally {
    loading.value = false;
  }
}

async function loadProductFilterOptions() {
  if (props.section !== "product") return;
  const params = {
    restaurant: selectedRestaurantId.value,
    page_size: 100,
  };
  const [categoryResponse, sectorResponse] = await Promise.all([
    api.get("/menu/categories/", { params }),
    api.get("/tables/sectors/", { params }),
  ]);
  categories.value = categoryResponse.data?.results || categoryResponse.data || [];
  sectors.value = sectorResponse.data?.results || sectorResponse.data || [];
}

async function handleRestaurantChange() {
  productFilters.category = "";
  productFilters.sector = "";
  await loadProductFilterOptions();
  await loadReport();
}

async function loadRestaurants() {
  loadingRestaurants.value = true;
  try {
    const response = await api.get("/restaurants/", {
      params: { page_size: 100 },
      skipRestaurantScope: true,
    });
    restaurants.value = response.data?.results || response.data || [];
    if (
      selectedRestaurantId.value
      && !restaurants.value.some((restaurant) => String(restaurant.id) === String(selectedRestaurantId.value))
    ) {
      selectedRestaurantId.value = "";
    }
  } finally {
    loadingRestaurants.value = false;
  }
}

async function exportCsv() {
  const params = new URLSearchParams({
    date_from: dateFrom.value,
    date_to: dateTo.value,
    export: "csv",
  });
  if (selectedRestaurantId.value) params.set("restaurant", selectedRestaurantId.value);
  const url = `${API_BASE_URL}/reports/sales/?${params}`;
  // Autenticação vai pelo cookie httpOnly (credentials: "include").
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) return;
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.setAttribute("download", `vendas_${dateFrom.value}_${dateTo.value}.csv`);
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function decimal(value) {
  return Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 3 });
}

function ymd(date) {
  const value = date instanceof Date ? date : new Date(date);
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

onMounted(async () => {
  await loadRestaurants();
  await loadProductFilterOptions();
  await loadReport();
});
</script>

<style scoped>
.reports-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.reports-view__filters {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
}

.reports-view__button {
  height: 38px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-card);
  color: var(--text-body);
  font: var(--weight-semibold) 13px/1 var(--font-sans);
}

.reports-view__range { width: min(100%, 290px); }
.reports-view__range :deep(.p-inputtext) { height: 38px; }

.reports-view__button {
  padding: 0 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.reports-view__button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.reports-view__button--outline {
  background: transparent;
  border-color: var(--border);
  color: var(--text-muted);
}

.reports-view__button--outline:hover:not(:disabled) {
  background: var(--surface-sunken);
  color: var(--text-body);
}

.reports-tabs {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid var(--border);
}

.reports-tab {
  padding: 10px 18px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font: var(--weight-semibold) 13px/1 var(--font-sans);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.15s, border-color 0.15s;
}

.reports-tab:hover {
  color: var(--text-body);
}

.reports-tab--active {
  color: var(--brand);
  border-bottom-color: var(--brand);
}

.responsive-one-col {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.reports-view__restaurant-filter {
  display: flex;
  align-items: center;
  min-width: 230px;
}

.reports-view__restaurant-filter select {
  width: 100%;
  height: 38px;
  padding: 8px 38px 8px 14px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  color: var(--text-body);
  font: var(--weight-medium) 13px/1.2 var(--font-sans);
}

.reports-view__select {
  min-width: 180px;
  height: 38px;
  padding: 8px 38px 8px 14px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--surface-raised);
  color: var(--text-body);
  font: var(--weight-medium) 13px/1.2 var(--font-sans);
}

.report-chart {
  position: relative;
  width: 100%;
  height: clamp(280px, 26vw, 320px);
  min-height: 280px;
}

.responsive-one-col .report-chart,
.report-chart--wide {
  height: clamp(300px, 28vw, 340px);
  min-height: 300px;
}

.responsive-two-col .report-chart {
  height: clamp(280px, 26vw, 320px);
}

.report-chart :deep(.p-chart),
.report-chart :deep(canvas) {
  width: 100% !important;
  height: 100% !important;
}

@media (max-width: 720px) {
  .reports-view { gap: 14px; }
  .reports-view__filters {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    padding: 10px;
  }
  .reports-view__restaurant-filter,
  .reports-view__range {
    grid-column: 1 / -1;
    width: 100%;
    min-width: 0;
    max-width: none;
  }
  .reports-view__select,
  .reports-view__button {
    width: 100%;
    min-width: 0;
    justify-content: center;
  }
  .reports-tabs {
    overflow-x: auto;
    scrollbar-width: none;
    scroll-snap-type: x proximity;
  }
  .reports-tabs::-webkit-scrollbar { display: none; }
  .reports-tab {
    flex: 0 0 auto;
    padding: 11px 14px;
    white-space: nowrap;
    scroll-snap-align: start;
  }
  .report-chart,
  .responsive-one-col .report-chart,
  .responsive-two-col .report-chart,
  .report-chart--wide {
    height: 230px;
    min-height: 230px;
  }
}

@media (max-width: 430px) {
  .reports-view__filters { grid-template-columns: 1fr; }
  .reports-view__restaurant-filter,
  .reports-view__range,
  .reports-view__select,
  .reports-view__button { grid-column: 1; }
  .report-chart,
  .responsive-one-col .report-chart,
  .responsive-two-col .report-chart,
  .report-chart--wide {
    height: 210px;
    min-height: 210px;
  }
}

:deep(.simple-table-wrap) {
  overflow-x: auto;
}

:deep(.simple-table) {
  width: 100%;
  border-collapse: collapse;
}

:deep(.simple-table th),
:deep(.simple-table td) {
  padding: 13px 18px;
  border-bottom: 1px solid var(--border-subtle);
  text-align: left;
  white-space: nowrap;
}

:deep(.simple-table th) {
  background: var(--surface-sunken);
  color: var(--text-subtle);
  font: var(--weight-bold) 11px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
}

:deep(.simple-table td) {
  color: var(--text-body);
  font: var(--weight-medium) 13px/1 var(--font-sans);
}

:deep(.simple-table .right) {
  text-align: right;
}

:deep(.simple-table .empty) {
  text-align: center;
  color: var(--text-muted);
}
</style>
