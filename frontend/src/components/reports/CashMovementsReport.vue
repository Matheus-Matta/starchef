<template>
  <div class="cash-report">
    <div class="responsive-kpi-grid">
      <StatCard label="Vendas em dinheiro" :value="money(summary.cash_sales)" tone="success" caption="Entrou na gaveta">
        <template #icon><AppIcon name="dollar-sign" :size="19" /></template>
      </StatCard>
      <StatCard label="Sangrias" :value="money(summary.withdrawals)" tone="danger" :caption="`${summary.pending_count || 0} pendente(s) de autorização`">
        <template #icon><AppIcon name="minus" :size="19" /></template>
      </StatCard>
      <StatCard label="Suprimentos" :value="money(summary.supplies)" tone="brand" :caption="`Aberturas: ${money(summary.opening)}`">
        <template #icon><AppIcon name="plus" :size="19" /></template>
      </StatCard>
      <StatCard label="Diferença nos fechamentos" :value="money(summary.difference_total)" :tone="Number(summary.difference_total || 0) < 0 ? 'danger' : 'neutral'" :caption="`${summary.sessions_with_difference || 0} de ${summary.sessions_count || 0} sessões com divergência`">
        <template #icon><AppIcon name="calculator" :size="19" /></template>
      </StatCard>
    </div>

    <div class="responsive-two-col">
      <Card title="Gaveta por dia" subtitle="Vendas em dinheiro, suprimentos e sangrias aprovadas">
        <div class="report-chart report-chart--wide"><Chart type="bar" :data="dayChart" :options="barOptions" /></div>
      </Card>
      <Card title="Resumo do período" padding="none">
        <ReportDataTable :rows="summaryRows" :columns="summaryColumns" />
      </Card>
    </div>

    <div class="responsive-two-col">
      <Card title="Por caixa" padding="none">
        <ReportDataTable :rows="report.by_station || []" :columns="stationColumns" />
      </Card>
      <Card title="Por operador" padding="none">
        <ReportDataTable :rows="report.by_operator || []" :columns="operatorColumns" />
      </Card>
    </div>

    <div class="responsive-one-col">
      <Card title="Sessões de caixa" subtitle="Abertas no período" padding="none">
        <ReportDataTable :rows="sessionRows" :columns="sessionColumns" />
      </Card>
      <Card title="Movimentações" subtitle="Cada lançamento, com quem fez, onde e quem autorizou" padding="none">
        <ReportDataTable :rows="movementRows" :columns="movementColumns" />
      </Card>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import Chart from "primevue/chart";

import AppIcon from "../AppIcon.vue";
import Card from "../display/Card.vue";
import StatCard from "../data/StatCard.vue";
import ReportDataTable from "../data/ReportDataTable.vue";

const props = defineProps({
  report: { type: Object, required: true },
  barOptions: { type: Object, required: true },
});

const summary = computed(() => props.report.summary || {});

const money = (value) =>
  Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const dateTime = (value) => (value ? new Date(value).toLocaleString("pt-BR") : "—");

const MOVEMENT_LABELS = {
  opening: "Abertura",
  sale: "Venda em dinheiro",
  withdrawal: "Sangria",
  supply: "Suprimento",
  closing: "Fechamento",
  adjustment: "Ajuste",
  refund: "Estorno",
};
const AUTHORIZATION_LABELS = {
  pending: "Pendente",
  cash_password: "Senha do caixa",
  manager: "Gerente",
  automatic: "Automática",
};
const SESSION_STATUS = {
  open: "Aberto",
  pending_manager_approval: "Aguardando aprovação",
  pending_closing: "Aguardando fechamento",
  closed: "Fechado",
  closed_with_difference: "Fechado com diferença",
  cancelled: "Cancelado",
  blocked: "Bloqueado",
};

const summaryColumns = [
  { key: "label", label: "Rubrica", sortable: false },
  { key: "value", label: "Valor", align: "right", type: "money", sortable: false },
];
const summaryRows = computed(() => [
  { label: "(+) Aberturas (troco inicial)", value: summary.value.opening },
  { label: "(+) Vendas em dinheiro", value: summary.value.cash_sales },
  { label: "(+) Suprimentos", value: summary.value.supplies },
  { label: "(-) Sangrias", value: summary.value.withdrawals },
  { label: "(-) Troco de cartão/PIX", value: summary.value.change_given },
  { label: "(-) Estornos em dinheiro", value: summary.value.refunds },
  { label: "(=) Saldo líquido movimentado", value: summary.value.net },
]);

const stationColumns = [
  { key: "cash_station_name", label: "Caixa" },
  { key: "count", label: "Movimentos", align: "right" },
  { key: "supplies", label: "Suprimentos", align: "right", type: "money" },
  { key: "withdrawals", label: "Sangrias", align: "right", type: "money" },
  { key: "total", label: "Saldo líquido", align: "right", type: "money" },
];
const operatorColumns = [
  { key: "operator_name", label: "Operador" },
  { key: "count", label: "Movimentos", align: "right" },
  { key: "supplies", label: "Suprimentos", align: "right", type: "money" },
  { key: "withdrawals", label: "Sangrias", align: "right", type: "money" },
  { key: "total", label: "Saldo líquido", align: "right", type: "money" },
];
const sessionColumns = [
  { key: "cash_station_name", label: "Caixa" },
  { key: "operator_name", label: "Operador" },
  { key: "terminal_label", label: "Terminal" },
  { key: "opened", label: "Abertura" },
  { key: "closed", label: "Fechamento" },
  { key: "status", label: "Status" },
  { key: "expected_amount", label: "Esperado", align: "right", type: "money" },
  { key: "actual_amount", label: "Contado", align: "right", type: "money" },
  { key: "difference_amount", label: "Diferença", align: "right", type: "money" },
];
const sessionRows = computed(() =>
  (props.report.sessions || []).map((row) => ({
    ...row,
    opened: dateTime(row.opened_at),
    closed: dateTime(row.closed_at),
    status: SESSION_STATUS[row.status] || row.status,
  })),
);
const movementColumns = [
  { key: "when", label: "Data" },
  { key: "cash_station_name", label: "Caixa" },
  { key: "type", label: "Movimento" },
  { key: "amount", label: "Valor", align: "right", type: "money" },
  { key: "reason", label: "Motivo" },
  { key: "destination", label: "Destino/Origem" },
  { key: "operator_name", label: "Operador" },
  { key: "terminal_label", label: "Terminal" },
  { key: "authorization", label: "Autorização" },
  { key: "authorized_by_name", label: "Autorizado por" },
  { key: "order", label: "Pedido" },
];
const movementRows = computed(() =>
  (props.report.movements || []).map((row) => ({
    ...row,
    when: dateTime(row.created_at),
    type: MOVEMENT_LABELS[row.movement_type] || row.movement_type,
    authorization: AUTHORIZATION_LABELS[row.authorization] || row.authorization,
    order: row.order_sequence ? `#${row.order_sequence}${row.payment_method_name ? ` · ${row.payment_method_name}` : ""}` : "—",
  })),
);

const dayChart = computed(() => {
  const rows = props.report.by_day || [];
  return {
    labels: rows.map((row) => (row.day ? new Date(`${row.day}T00:00:00`).toLocaleDateString("pt-BR") : "—")),
    datasets: [
      { label: "Vendas em dinheiro", data: rows.map((r) => Number(r.cash_sales || 0)), backgroundColor: "#22C55E", borderRadius: 6 },
      { label: "Suprimentos", data: rows.map((r) => Number(r.supplies || 0)), backgroundColor: "#3B82F6", borderRadius: 6 },
      { label: "Sangrias", data: rows.map((r) => Number(r.withdrawals || 0)), backgroundColor: "#EF4444", borderRadius: 6 },
    ],
  };
});
</script>
