<template>
  <div class="cash-summary">
    <StatCard label="Abertura" :value="money(totals.opening)" tone="neutral" caption="Troco inicial" />
    <StatCard label="Vendas em dinheiro" :value="money(totals.cashSales)" tone="success" :caption="`${session.sales?.length || 0} recebimento(s) no total`" />
    <StatCard label="Suprimentos" :value="money(totals.supplies)" tone="brand" caption="Entradas adicionais" />
    <StatCard label="Sangrias e saídas" :value="money(totals.withdrawals)" tone="danger" caption="Retiradas aprovadas" />
    <StatCard label="Esperado na gaveta" :value="money(expected)" tone="info" :caption="`Saldo atual: ${money(session.current_balance)}`" />
    <StatCard label="Diferença" :value="nullableMoney(session.difference_amount)" :tone="differenceTone" :caption="session.actual_amount == null ? 'Sem conferência final' : `Contado: ${money(session.actual_amount)}`" />
  </div>
</template>

<script setup>
import { computed } from "vue";
import StatCard from "../data/StatCard.vue";

const props = defineProps({ session: { type: Object, required: true } });
const approved = computed(() => (props.session.movements || []).filter((item) => item.status === "approved"));
const totals = computed(() => approved.value.reduce((sum, item) => {
  const amount = Number(item.amount || 0);
  if (item.movement_type === "opening") sum.opening += amount;
  if (item.movement_type === "sale") sum.cashSales += amount;
  if (item.movement_type === "supply") sum.supplies += amount;
  if (["withdrawal", "refund"].includes(item.movement_type)) sum.withdrawals += Math.abs(amount);
  return sum;
}, { opening: 0, cashSales: 0, supplies: 0, withdrawals: 0 }));
const expected = computed(() => props.session.expected_amount ?? props.session.current_balance ?? 0);
const differenceTone = computed(() => Number(props.session.difference_amount || 0) === 0 ? "neutral" : "danger");
const money = (value) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const nullableMoney = (value) => value === null || value === undefined ? "—" : money(value);
</script>

<style scoped>
.cash-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
@media(max-width:900px){.cash-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:520px){.cash-summary{grid-template-columns:1fr}}
</style>
