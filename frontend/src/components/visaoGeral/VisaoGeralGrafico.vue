<template>
  <Card title="Vendas" :subtitle="subtitulo">
    <div class="vg-barras" role="img" :aria-label="`Vendas ${subtitulo}`">
      <div v-for="barra in barras" :key="barra.rotulo" class="vg-barras__item" :title="`${barra.rotulo}: ${dinheiro(barra.valor)}`">
        <span class="vg-barras__valor">{{ compacto(barra.valor) }}</span>
        <div class="vg-barras__barra" :style="{ height: `${barra.altura}%` }" />
        <span class="vg-barras__rotulo">{{ barra.rotulo }}</span>
      </div>
    </div>
  </Card>
</template>

<script setup>
import { computed } from "vue";

import Card from "../display/Card.vue";
import { formatMoney } from "../../utils/format";

const props = defineProps({
  pontos: { type: Array, default: () => [] },
  periodo: { type: String, default: "dia" },
});

const dinheiro = formatMoney;
const subtitulo = computed(() => (props.periodo === "dia" ? "por hora, hoje" : "por dia"));

const barras = computed(() => {
  const maior = Math.max(...props.pontos.map((p) => Number(p.valor)), 0);
  return props.pontos.map((p) => ({
    ...p,
    altura: maior ? Math.max(6, Math.round((Number(p.valor) / maior) * 100)) : 6,
  }));
});

function compacto(valor) {
  const n = Number(valor || 0);
  if (n >= 1000) return `${(n / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
  return n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
}
</script>

<style scoped>
.vg-barras { display: flex; align-items: flex-end; gap: 8px; height: 200px; overflow-x: auto; padding-top: 18px; }
.vg-barras__item { display: flex; flex: 1 0 34px; flex-direction: column; align-items: center; justify-content: flex-end; gap: 4px; height: 100%; }
.vg-barras__barra { width: 100%; max-width: 44px; border-radius: 4px 4px 0 0; background: var(--brand); }
.vg-barras__valor { color: var(--text-muted); font: var(--weight-semibold) 10px/1 var(--font-sans); white-space: nowrap; }
.vg-barras__rotulo { color: var(--text-muted); font: var(--weight-medium) 11px/1 var(--font-sans); }
</style>
