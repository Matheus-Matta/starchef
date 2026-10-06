<template>
  <div class="coupons-report">
    <div class="responsive-kpi-grid">
      <StatCard label="Usos de cupom" :value="String(totals.uses || 0)" tone="brand" caption="Pedidos pagos com cupom">
        <template #icon><AppIcon name="ticket" :size="19" /></template>
      </StatCard>
      <StatCard label="Total descontado" :value="money(totals.discount)" tone="danger" caption="O que os cupons abateram">
        <template #icon><AppIcon name="minus" :size="19" /></template>
      </StatCard>
      <StatCard label="Total vendido" :value="money(totals.gross)" tone="neutral" caption="Antes do desconto">
        <template #icon><AppIcon name="receipt-text" :size="19" /></template>
      </StatCard>
      <StatCard label="Total líquido" :value="money(totals.net)" tone="success" caption="O que os pedidos cobraram">
        <template #icon><AppIcon name="dollar-sign" :size="19" /></template>
      </StatCard>
    </div>

    <div class="responsive-one-col">
      <Card title="Por cupom" subtitle="Clique em um cupom para ver cada uso" padding="none">
        <ReportDataTable :rows="report.by_coupon || []" :columns="couponColumns" row-clickable @row-click="openCoupon" />
      </Card>
      <Card v-if="selected" :title="`Usos do cupom ${selected.code}`" :subtitle="selected.name || ''" padding="none">
        <ReportDataTable :rows="redemptionRows" :columns="redemptionColumns" />
      </Card>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import AppIcon from "../AppIcon.vue";
import Card from "../display/Card.vue";
import StatCard from "../data/StatCard.vue";
import ReportDataTable from "../data/ReportDataTable.vue";
import { reportService } from "../../services/reportService";

const props = defineProps({
  report: { type: Object, required: true },
  // Os mesmos filtros da tela: o detalhe precisa do mesmo período.
  filters: { type: Object, default: () => ({}) },
});

const selected = ref(null);
const redemptions = ref([]);

const totals = computed(() => props.report.totals || {});

const money = (value) =>
  Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

const couponColumns = [
  { key: "code", label: "Cupom" },
  { key: "name", label: "Nome" },
  { key: "uses", label: "Usos", align: "right" },
  { key: "gross", label: "Total vendido", align: "right", type: "money" },
  { key: "discount", label: "Total descontado", align: "right", type: "money" },
  { key: "net", label: "Total líquido", align: "right", type: "money" },
];

const redemptionColumns = [
  { key: "date", label: "Data" },
  { key: "order", label: "Pedido" },
  { key: "document", label: "CPF" },
  { key: "net", label: "Valor do pedido", align: "right", type: "money" },
  { key: "discount", label: "Descontado", align: "right", type: "money" },
];

const redemptionRows = computed(() =>
  redemptions.value.map((row) => ({
    ...row,
    date: new Date(row.date).toLocaleString("pt-BR"),
    order: `#${row.order_sequence}`,
    document: row.document || "—",
  })),
);

async function openCoupon(row) {
  selected.value = row;
  const data = await reportService.getCouponRedemptions(row.coupon_id, props.filters);
  redemptions.value = data.redemptions || [];
}

// Período ou restaurante mudou: o detalhe aberto ficaria de outro recorte.
watch(
  () => props.report,
  () => {
    selected.value = null;
    redemptions.value = [];
  },
);
</script>
