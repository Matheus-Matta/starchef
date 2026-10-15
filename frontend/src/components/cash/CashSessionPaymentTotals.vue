<template>
  <Card title="Totais por forma de pagamento" subtitle="Para conferir com a maquininha e o extrato do banco">
    <p v-if="!rows.length" class="payment-totals__empty">Nenhum recebimento nesta sessão.</p>
    <table v-else class="payment-totals">
      <thead><tr><th>Forma</th><th class="num">Recebimentos</th><th class="num">Troco</th><th class="num">Total</th></tr></thead>
      <tbody>
        <tr v-for="row in rows" :key="row.payment_method"><td>{{ row.payment_method_name || '—' }}</td><td class="num">{{ row.count }}</td><td class="num">{{ Number(row.change) ? money(row.change) : '—' }}</td><td class="num">{{ money(row.amount) }}</td></tr>
      </tbody>
      <tfoot><tr><th>Total geral</th><th class="num">{{ count }}</th><th></th><th class="num">{{ money(total) }}</th></tr></tfoot>
    </table>
  </Card>
</template>

<script setup>
import Card from "../display/Card.vue";

/* Os totais vêm somados do servidor (`payment_totals`): a tela não soma
 * dinheiro, para o número aqui ser o mesmo do relatório e do CSV. */
defineProps({ rows: { type: Array, default: () => [] }, total: { type: [String, Number], default: 0 }, count: { type: Number, default: 0 } });
const money = (value) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
</script>

<style scoped>
.payment-totals{width:100%;border-collapse:collapse}.payment-totals th,.payment-totals td{padding:9px 10px;border-bottom:1px solid var(--border);text-align:left}.payment-totals thead th{color:var(--text-muted);font-size:12px;font-weight:600;text-transform:uppercase}.payment-totals tfoot th{border-bottom:0;font-size:15px}.payment-totals .num{text-align:right;white-space:nowrap}.payment-totals__empty{margin:0;color:var(--text-muted)}
</style>
