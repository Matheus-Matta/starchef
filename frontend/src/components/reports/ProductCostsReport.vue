<template>
  <div class="product-costs-report report-panel">
    <div class="responsive-kpi-grid">
      <StatCard label="Vendido" :value="money(totals.revenue)" tone="success" caption="Receita dos itens no período">
        <template #icon><AppIcon name="dollar-sign" :size="19" /></template>
      </StatCard>
      <StatCard label="Custo" :value="money(totals.cost)" tone="danger" caption="Custo do que foi vendido">
        <template #icon><AppIcon name="minus" :size="19" /></template>
      </StatCard>
      <StatCard label="Margem bruta" :value="money(totals.margin)" tone="brand" :caption="marginCaption">
        <template #icon><AppIcon name="trending-up" :size="19" /></template>
      </StatCard>
    </div>

    <div class="responsive-one-col">
      <Card title="Custo × venda por produto" :subtitle="subtitle" padding="none">
        <ReportDataTable :rows="rows" :columns="columns" />
      </Card>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

import AppIcon from "../AppIcon.vue";
import Card from "../display/Card.vue";
import StatCard from "../data/StatCard.vue";
import ReportDataTable from "../data/ReportDataTable.vue";

const props = defineProps({ report: { type: Object, required: true } });

const SOURCE_LABELS = { baixa: "Baixa de estoque", cadastro: "Cadastro (estimado)", misto: "Baixa + cadastro" };

const totals = computed(() => props.report.totals || {});
const money = (value) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const marginCaption = computed(() => {
  const receita = Number(totals.value.revenue || 0);
  if (!receita) return "Sem vendas no período";
  return `${((Number(totals.value.margin || 0) / receita) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% do vendido`;
});
const subtitle = "O custo vem da baixa de estoque da venda (custo da época). Sem baixa, usa o custo do cadastro.";

const columns = [
  { key: "code", label: "Código" },
  { key: "product_name", label: "Produto" },
  { key: "quantity", label: "Qtd", align: "right", type: "decimal", digits: 3 },
  { key: "revenue", label: "Vendido", align: "right", type: "money" },
  { key: "cost", label: "Custo", align: "right", type: "money" },
  { key: "margin", label: "Margem", align: "right", type: "money" },
  { key: "margin_percent", label: "Margem %", align: "right", type: "decimal" },
  { key: "source", label: "Origem do custo" },
];

const rows = computed(() =>
  (props.report.by_product || []).map((row) => ({ ...row, source: SOURCE_LABELS[row.cost_source] || row.cost_source })),
);
</script>
