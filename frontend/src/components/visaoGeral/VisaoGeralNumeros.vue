<template>
  <div class="vg-numeros">
    <section v-for="grupo in grupos" :key="grupo.chave" class="vg-numeros__grupo">
      <header>
        <div>
          <h2>{{ grupo.titulo }}</h2>
          <p>{{ grupo.descricao }}</p>
        </div>
      </header>
      <div class="responsive-kpi-grid">
        <StatCard
          v-for="cartao in grupo.cartoes" :key="cartao.chave" :label="cartao.rotulo" :value="cartao.valor"
          :tone="cartao.tom" :caption="cartao.legenda"
        >
          <template #icon><AppIcon :name="cartao.icone" :size="19" /></template>
        </StatCard>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from "vue";

import AppIcon from "../AppIcon.vue";
import StatCard from "../data/StatCard.vue";
import { cartoesDaVisaoGeral } from "./cartoes";

const props = defineProps({
  vendas: { type: Object, default: () => ({}) },
  comandas: { type: Object, default: () => ({}) },
  periodo: { type: String, default: "dia" },
});

const cartoes = computed(() => cartoesDaVisaoGeral(props.vendas, props.comandas));
const rotuloPeriodo = computed(() => ({ dia: "Hoje", semana: "Nesta semana", mes: "Neste mês" })[props.periodo] || "No período");
const grupos = computed(() => [
  {
    chave: "periodo",
    titulo: rotuloPeriodo.value,
    descricao: "Vendas, pedidos e resultados do período selecionado.",
    cartoes: cartoes.value.filter((cartao) => cartao.grupo === "periodo"),
  },
  {
    chave: "agora",
    titulo: "Comandas",
    descricao: "O que está em uso agora e o movimento no período selecionado.",
    cartoes: cartoes.value.filter((cartao) => cartao.grupo === "agora"),
  },
]);
</script>

<style scoped>
.vg-numeros { display: flex; flex-direction: column; gap: 22px; }
.vg-numeros__grupo { display: flex; flex-direction: column; gap: 12px; }
.vg-numeros__grupo header { display: flex; align-items: end; justify-content: space-between; gap: 16px; }
.vg-numeros__grupo h2 { margin: 0; color: var(--text-strong); font: var(--weight-bold) 18px/1.2 var(--font-sans); }
.vg-numeros__grupo p { margin: 3px 0 0; color: var(--text-muted); font: var(--weight-medium) 12px/1.4 var(--font-sans); }
</style>
