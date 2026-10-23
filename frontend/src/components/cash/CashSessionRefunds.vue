<template>
  <Card v-if="rows.length" title="Estornos" subtitle="Pedidos pagos e depois cancelados: o valor saiu do caixa e voltou ao cliente">
    <table class="cash-refunds">
      <thead><tr><th>Pedido</th><th>Forma</th><th>Motivo</th><th class="num">Valor</th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id"><td>#{{ row.order_sequence }}</td><td>{{ row.payment_method_name || '—' }}</td><td>{{ row.cancel_reason || '—' }}</td><td class="num">{{ money(row.amount) }}</td></tr>
      </tbody>
      <tfoot><tr><th colspan="3">Total estornado</th><th class="num">{{ money(total) }}</th></tr></tfoot>
    </table>
  </Card>
</template>

<script setup>
import Card from "../display/Card.vue";

/* Somado pelo servidor (`refunds_total`), como os totais por forma. */
defineProps({ rows: { type: Array, default: () => [] }, total: { type: [String, Number], default: 0 } });
const money = (value) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
</script>

<style scoped>
.cash-refunds{width:100%;border-collapse:collapse}.cash-refunds th,.cash-refunds td{padding:9px 10px;border-bottom:1px solid var(--border);text-align:left}.cash-refunds thead th{color:var(--text-muted);font-size:12px;font-weight:600;text-transform:uppercase}.cash-refunds tfoot th{border-bottom:0;font-size:15px}.cash-refunds .num{text-align:right;white-space:nowrap}
</style>
