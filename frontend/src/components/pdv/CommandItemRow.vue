<template>
  <li class="pdv-item">
    <span class="pdv-num pdv-muted">{{ quantidade }}</span>
    <span>
      {{ item.product_name }}
      <em v-if="item.customer_note" class="linha__nota">{{ item.customer_note }}</em>
      <!-- No histórico, o estado é a informação principal: é ele que diz se o
           item ainda está na conta ou se já foi pago. -->
      <em v-if="mostrarEstado" class="linha__nota">{{ estado }}</em>
    </span>
    <span class="pdv-num">{{ valor }}</span>
  </li>
</template>

<script setup>
/** Uma linha de item da comanda. */
import { computed } from "vue";

const props = defineProps({
  item: { type: Object, required: true },
  mostrarEstado: { type: Boolean, default: false },
});

/** Produto por quilo mostra o peso; o resto mostra a contagem. */
const quantidade = computed(() => {
  const bruto = Number(props.item.quantity || 0);
  return Number.isInteger(bruto) ? `${bruto}x` : `${bruto.toFixed(3)} kg`;
});

const valor = computed(() =>
  Number(props.item.total_price || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  }),
);

/**
 * O estado do item NA COMANDA — financeiro, não de produção.
 *
 * Um item pode estar `delivered` na cozinha (o prato está na mesa) e continuar
 * ABERTO aqui, porque ninguém pagou. É o caso normal durante a refeição.
 */
const estado = computed(() =>
  props.item.command_status === "closed" ? "fechado" : "aberto",
);
</script>

<style scoped>
.linha__nota {
  display: block;
  font-size: 11px;
  font-style: normal;
  color: var(--text-color-secondary, #6b7280);
}
</style>
