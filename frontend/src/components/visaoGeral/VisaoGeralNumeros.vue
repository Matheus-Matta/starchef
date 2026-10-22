<template>
  <div v-if="cartoes.length" class="responsive-kpi-grid">
    <StatCard
      v-for="cartao in cartoes" :key="cartao.chave" :label="cartao.rotulo" :value="cartao.valor"
      :tone="cartao.tom" :caption="cartao.legenda"
    >
      <template #icon><AppIcon :name="cartao.icone" :size="19" /></template>
    </StatCard>
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
});

const cartoes = computed(() => cartoesDaVisaoGeral(props.vendas, props.comandas));
</script>
