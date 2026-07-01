<template>
  <div class="reports-view">
    <div class="reports-view__filters">
      <input v-model="dateFrom" type="date" class="reports-view__input" />
      <input v-model="dateTo" type="date" class="reports-view__input" />
      <button class="reports-view__button" type="button" :disabled="loading" @click="loadReport">
        {{ loading ? "Carregando..." : "Atualizar" }}
      </button>
      <button class="reports-view__button reports-view__button--outline" type="button" :disabled="loading" @click="exportCsv">
        <AppIcon name="download" :size="14" /> Exportar CSV
      </button>
    </div>

    <div class="responsive-kpi-grid">
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

    <div class="reports-tabs">
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

    <div v-if="activeTab === 'payment'" class="responsive-two-col">
      <Card title="Por forma de pagamento" padding="none">
        <SimpleTable :rows="paymentRows" :columns="paymentColumns" />
      </Card>
      <Card title="Por filial" padding="none">
        <SimpleTable :rows="branchRows" :columns="branchColumns" />
      </Card>
    </div>

    <div v-if="activeTab === 'waiter'" class="responsive-one-col">
      <Card title="Vendas por garcom" padding="none">
        <SimpleTable :rows="waiterRows" :columns="waiterColumns" />
      </Card>
    </div>

    <div v-if="activeTab === 'product'" class="responsive-one-col">
      <Card title="Vendas por produto" padding="none">
        <SimpleTable :rows="productRows" :columns="productColumns" />
      </Card>
    </div>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref } from "vue";

import AppIcon from "../components/AppIcon.vue";
import StatCard from "../components/data/StatCard.vue";
import Card from "../components/display/Card.vue";
import { api, API_BASE_URL } from "../services/api";
import { getAccessToken } from "../services/tokenStorage";

const today = new Date().toISOString().slice(0, 10);
const dateFrom = ref(today);
const dateTo = ref(today);
const report = ref({});
const loading = ref(false);
const activeTab = ref("payment");

const tabs = [
  { id: "payment", label: "Por pagamento e filial" },
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

const paymentColumns = [
  { key: "name", label: "Forma" },
  { key: "count", label: "Pagamentos" },
  { key: "total", label: "Total", align: "right", type: "money" },
];
const branchColumns = [
  { key: "name", label: "Filial" },
  { key: "count", label: "Pedidos" },
  { key: "total", label: "Total", align: "right", type: "money" },
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
  { key: "total", label: "Total", align: "right", type: "money" },
];

function SimpleTable(props) {
  function cellValue(row, column) {
    const val = column.key.split(".").reduce((obj, k) => obj?.[k], row);
    if (column.type === "money") {
      return Number(val || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }
    return val ?? "-";
  }

  const rows = props.rows.map((row, i) =>
    h("tr", { key: i }, props.columns.map((col) =>
      h("td", { key: col.key, class: { right: col.align === "right" } }, cellValue(row, col)),
    )),
  );

  if (!props.rows.length) {
    rows.push(h("tr", { key: "empty" }, [h("td", { colspan: props.columns.length, class: "empty" }, "Sem dados no periodo.")]));
  }

  return h("div", { class: "simple-table-wrap" }, [
    h("table", { class: "simple-table" }, [
      h("thead", {}, [h("tr", {}, props.columns.map((col) => h("th", { key: col.key, class: { right: col.align === "right" } }, col.label)))]),
      h("tbody", {}, rows),
    ]),
  ]);
}
SimpleTable.props = { rows: { type: Array, required: true }, columns: { type: Array, required: true } };

const paymentRows = computed(() =>
  (report.value.by_payment_method || []).map((row) => ({
    name: row.payments__payment_method__name || "Nao informado",
    count: row.count,
    total: row.total,
  })),
);
const branchRows = computed(() =>
  (report.value.by_branch || []).map((row) => ({
    name: row.branch__name || "Sem filial",
    count: row.count,
    total: row.total,
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
  })),
);

async function loadReport() {
  loading.value = true;
  try {
    const response = await api.get("/reports/sales/", {
      params: { date_from: dateFrom.value, date_to: dateTo.value },
    });
    report.value = response.data || {};
  } finally {
    loading.value = false;
  }
}

function exportCsv() {
  const token = getAccessToken();
  const base = API_BASE_URL;
  const params = new URLSearchParams({
    date_from: dateFrom.value,
    date_to: dateTo.value,
    export: "csv",
  });
  const url = `${base}/reports/sales/?${params}`;
  const a = document.createElement("a");
  a.href = url;
  a.setAttribute("download", `vendas_${dateFrom.value}_${dateTo.value}.csv`);
  // Pass token via URL is not ideal, so open in new tab and let the browser handle it
  const win = window.open("", "_blank");
  if (win) {
    const form = win.document.createElement("form");
    form.method = "GET";
    form.action = url;
    const tokenInput = win.document.createElement("input");
    tokenInput.type = "hidden";
    tokenInput.name = "Authorization";
    tokenInput.value = `Bearer ${token}`;
    form.appendChild(tokenInput);
    win.document.body.appendChild(form);
    // Use fetch to download
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => res.blob())
      .then((blob) => {
        const blobUrl = URL.createObjectURL(blob);
        a.href = blobUrl;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
        win.close();
      });
  }
}

function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

onMounted(loadReport);
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
}

.reports-view__input,
.reports-view__button {
  height: 38px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-card);
  color: var(--text-body);
  font: var(--weight-semibold) 13px/1 var(--font-sans);
}

.reports-view__input {
  padding: 0 10px;
}

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
  gap: 16px;
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
