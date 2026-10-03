<template>
  <div class="product-sales-detail">
    <div class="product-sales-detail__heading">
      <Button label="Voltar aos produtos" icon="pi pi-arrow-left" severity="secondary" text @click="router.back()" />
      <h1>{{ report.product || "Vendas do produto" }}</h1>
      <p>{{ report.sales?.length || 0 }} lançamentos · {{ money(report.total) }}</p>
    </div>
    <Card title="Saídas registradas" padding="none">
      <ReportDataTable :rows="rows" :columns="columns" />
    </Card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Card from "../components/display/Card.vue";
import ReportDataTable from "../components/data/ReportDataTable.vue";
import { reportService } from "../services/reportService";

const route = useRoute();
const router = useRouter();
const report = ref({ sales: [] });
const columns = [
  { key: "order", label: "Pedido" },
  { key: "command", label: "Comanda" },
  { key: "operator", label: "Quem lançou" },
  { key: "operator_code", label: "Código do operador" },
  { key: "cashier", label: "Caixa que finalizou" },
  { key: "quantity", label: "Qtd.", align: "right" },
  { key: "item_total", label: "Valor do item", align: "right", type: "money" },
  { key: "order_total", label: "Total do pedido", align: "right", type: "money" },
  { key: "closed_at", label: "Finalizado em" },
];
const rows = computed(() => (report.value.sales || []).map((sale) => ({
  order: `#${sale.order_sequence}`,
  command: sale.command_number ? `#${sale.command_number}${sale.command_name ? ` · ${sale.command_name}` : ""}` : "—",
  operator: sale.operator,
  operator_code: sale.operator_code || "—",
  cashier: sale.cashier,
  quantity: Number(sale.quantity || 0).toLocaleString("pt-BR"),
  item_total: sale.item_total,
  order_total: sale.order_total,
  closed_at: sale.closed_at ? new Date(sale.closed_at).toLocaleString("pt-BR") : "—",
})));

function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

onMounted(async () => {
  report.value = await reportService.getProductSales(route.params.productId, route.query);
});
</script>

<style scoped>
.product-sales-detail { display: flex; flex-direction: column; gap: var(--page-section-gap); }
.product-sales-detail__heading h1 { margin: 8px 0 4px; font-size: 1.5rem; }
.product-sales-detail__heading p { margin: 0; color: var(--text-muted); }
</style>
