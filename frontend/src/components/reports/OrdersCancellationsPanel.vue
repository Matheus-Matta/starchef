<template>
  <div class="cancellations-panel">
    <div class="responsive-kpi-grid">
      <StatCard label="Valor cancelado" :value="money(report.cancelled_total)" tone="danger" :caption="`${report.orders_cancelled || 0} pedido(s) no período`">
        <template #icon><AppIcon name="x" :size="19" /></template>
      </StatCard>
      <StatCard label="Taxa de cancelamento" :value="`${Number(report.cancelled_rate || 0).toLocaleString('pt-BR')}%`" tone="warning" caption="Cancelados sobre todos os pedidos">
        <template #icon><AppIcon name="percentage" :size="19" /></template>
      </StatCard>
      <StatCard label="Itens retirados" :value="String(report.voided_items_count || 0)" tone="neutral" :caption="money(report.voided_items_total)">
        <template #icon><AppIcon name="minus" :size="19" /></template>
      </StatCard>
      <StatCard label="Quem mais cancela" :value="topCanceller.name" tone="brand" :caption="`${topCanceller.count} cancelamento(s)`">
        <template #icon><AppIcon name="users" :size="19" /></template>
      </StatCard>
    </div>

    <div class="responsive-two-col">
      <Card title="Cancelamentos por hora do dia">
        <div class="report-chart report-chart--wide"><Chart type="bar" :data="hourChart" :options="barOptions" /></div>
      </Card>
      <Card title="Como foram autorizados" padding="none">
        <ReportDataTable :rows="report.cancelled_by_authorization || []" :columns="authorizationColumns" />
      </Card>
    </div>

    <div class="responsive-one-col">
      <Card title="Pedidos cancelados" subtitle="Quem cancelou, quem liberou, quando e quanto" padding="none">
        <ReportDataTable :rows="cancelledRows" :columns="cancelledColumns" />
      </Card>
      <Card title="Itens retirados da conta" subtitle="Desistências e cortesias em pedidos que seguiram" padding="none">
        <ReportDataTable :rows="voidedRows" :columns="voidedColumns" />
      </Card>
      <Card title="Cancelamentos por operador" padding="none">
        <ReportDataTable :rows="report.cancelled_by_user || []" :columns="userColumns" />
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

const money = (value) =>
  Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const dateTime = (value) => (value ? new Date(value).toLocaleString("pt-BR") : "—");

const topCanceller = computed(() => {
  const first = (props.report.cancelled_by_user || [])[0];
  return first ? { name: first.name, count: first.count } : { name: "—", count: 0 };
});

const authorizationColumns = [
  { key: "label", label: "Autorização" },
  { key: "count", label: "Pedidos", align: "right" },
  { key: "total", label: "Valor", align: "right", type: "money" },
];
const userColumns = [
  { key: "name", label: "Operador" },
  { key: "count", label: "Cancelamentos", align: "right" },
  { key: "total", label: "Valor", align: "right", type: "money" },
];
const cancelledColumns = [
  { key: "sequence", label: "Pedido", align: "right" },
  { key: "order_type_label", label: "Tipo" },
  { key: "reference", label: "Referência" },
  { key: "opened", label: "Aberto em" },
  { key: "cancelled", label: "Cancelado em" },
  { key: "minutes", label: "Min. aberto", align: "right" },
  { key: "cancelled_by", label: "Cancelado por" },
  { key: "authorization_label", label: "Autorização" },
  { key: "authorized_by", label: "Autorizado por" },
  { key: "reason", label: "Motivo" },
  { key: "items_count", label: "Itens", align: "right" },
  { key: "total", label: "Valor", align: "right", type: "money" },
];
const cancelledRows = computed(() =>
  (props.report.cancelled_orders || []).map((row) => ({
    ...row,
    opened: dateTime(row.opened_at),
    cancelled: dateTime(row.cancelled_at),
    minutes: row.minutes_open ?? "—",
    authorized_by: row.authorized_by || "—",
  })),
);
const voidedColumns = [
  { key: "order_sequence", label: "Pedido", align: "right" },
  { key: "product_name", label: "Produto" },
  { key: "quantity", label: "Qtd", align: "right", type: "decimal" },
  { key: "total_price", label: "Valor", align: "right", type: "money" },
  { key: "kind", label: "Tipo" },
  { key: "reason", label: "Motivo" },
  { key: "voided_by", label: "Retirado por" },
  { key: "when", label: "Quando" },
  { key: "stage", label: "Cozinha" },
];
const voidedRows = computed(() =>
  (props.report.voided_items || []).map((row) => ({
    ...row,
    when: dateTime(row.voided_at),
    stage: row.before_kitchen ? "Antes de enviar" : "Já em produção",
  })),
);

const hourChart = computed(() => {
  const rows = props.report.cancelled_by_hour || [];
  return {
    labels: rows.map((row) => `${String(row.hour).padStart(2, "0")}h`),
    datasets: [
      { label: "Cancelamentos", data: rows.map((r) => Number(r.count || 0)), backgroundColor: "#EF4444", borderRadius: 6 },
    ],
  };
});
</script>

<style scoped>
.cancellations-panel{display:flex;flex-direction:column;gap:20px;padding-top:4px}
@media(max-width:720px){.cancellations-panel{gap:14px;padding-top:2px}}
</style>
