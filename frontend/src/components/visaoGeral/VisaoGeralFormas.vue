<template>
  <Card title="Formas de pagamento" :subtitle="`${dinheiro(total)} recebidos`">
    <div class="vg-formas">
      <div
        class="vg-formas__rosca" :style="{ background: rosca }" role="img"
        :aria-label="formas.map((f) => `${f.forma} ${f.pct}%`).join(', ')"
      />
      <ul class="vg-formas__legenda">
        <li v-for="forma in formas" :key="forma.forma">
          <span class="vg-formas__cor" :style="{ background: forma.cor }" />
          <span class="vg-formas__nome">{{ forma.forma }}</span>
          <span class="vg-formas__pct">{{ forma.pct }}%</span>
          <span class="vg-formas__valor">{{ dinheiro(forma.valor) }}</span>
        </li>
      </ul>
    </div>
  </Card>
</template>

<script setup>
import { computed } from "vue";

import Card from "../display/Card.vue";
import { formatMoney } from "../../utils/format";

const props = defineProps({ itens: { type: Array, default: () => [] } });

const CORES = ["var(--brand)", "var(--success)", "var(--info)", "var(--warning)", "var(--danger)", "var(--text-muted)"];
const dinheiro = formatMoney;

const total = computed(() => props.itens.reduce((soma, f) => soma + Number(f.valor), 0));

const formas = computed(() => props.itens.map((f, i) => ({
  ...f,
  cor: CORES[i % CORES.length],
  pct: total.value ? Math.round((Number(f.valor) / total.value) * 1000) / 10 : 0,
})));

// Rosca com `conic-gradient`: sem biblioteca de gráfico só para isto.
const rosca = computed(() => {
  let inicio = 0;
  const fatias = formas.value.map((f) => {
    const fim = inicio + (total.value ? (Number(f.valor) / total.value) * 100 : 0);
    const fatia = `${f.cor} ${inicio}% ${fim}%`;
    inicio = fim;
    return fatia;
  });
  return `conic-gradient(${fatias.join(", ")})`;
});
</script>

<style scoped>
.vg-formas { display: flex; flex-wrap: wrap; align-items: center; gap: 20px; }
.vg-formas__rosca {
  flex: none; width: 140px; height: 140px; border-radius: 50%;
  -webkit-mask: radial-gradient(circle, transparent 0 44px, #000 45px);
  mask: radial-gradient(circle, transparent 0 44px, #000 45px);
}
.vg-formas__legenda { display: grid; flex: 1 1 220px; gap: 10px; margin: 0; padding: 0; list-style: none; }
.vg-formas__legenda li { display: grid; grid-template-columns: 10px 1fr auto auto; align-items: center; gap: 8px; }
.vg-formas__cor { width: 10px; height: 10px; border-radius: 2px; }
.vg-formas__nome { color: var(--text-body); font: var(--weight-semibold) 13px/1.2 var(--font-sans); }
.vg-formas__pct { color: var(--text-muted); font: var(--weight-medium) 12px/1 var(--font-sans); }
.vg-formas__valor { color: var(--text-strong); font: var(--weight-bold) 13px/1 var(--font-sans); font-variant-numeric: tabular-nums; }
</style>
