<template>
  <div class="dashboard-view">
    <header class="visao-geral__cabecalho">
      <div>
        <span>RELATÓRIO OPERACIONAL</span>
        <h1>Visão geral</h1>
        <p>Vendas, pedidos, comandas, pagamentos, caixas e estoque em uma única leitura.</p>
      </div>
    </header>

    <VisaoGeralFiltros
      v-model:periodo="periodo"
      v-model:restaurante="restaurante"
      :restaurantes="restaurantes"
      :pode-escolher-restaurante="podeEscolherRestaurante"
      :intervalo="dados.periodo"
    />

    <div v-if="erro" class="visao-geral__alerta">{{ erro }}</div>
    <div v-else-if="semMovimento" class="visao-geral__vazio">
      {{ carregando ? "Carregando…" : "Nenhum movimento no período." }}
    </div>

    <VisaoGeralNumeros
      :vendas="dados.vendas" :comandas="dados.comandas"
      :periodo="dados.periodo?.nome || periodo"
    />

    <div v-if="dados.grafico || dados.formas_de_pagamento" class="responsive-two-col">
      <VisaoGeralGrafico v-if="dados.grafico" :pontos="dados.grafico" :periodo="periodo" />
      <VisaoGeralFormas v-if="dados.formas_de_pagamento" :itens="dados.formas_de_pagamento" />
    </div>

    <VisaoGeralCaixas v-if="dados.caixas_abertos" :caixas="dados.caixas_abertos" />

    <div v-if="dados.produtos_vendidos || dados.baixas_de_estoque" class="responsive-two-col">
      <VisaoGeralSaidas :produtos="dados.produtos_vendidos || []" :baixas="dados.baixas_de_estoque || []" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from "vue";

import VisaoGeralCaixas from "../components/visaoGeral/VisaoGeralCaixas.vue";
import VisaoGeralFiltros from "../components/visaoGeral/VisaoGeralFiltros.vue";
import VisaoGeralFormas from "../components/visaoGeral/VisaoGeralFormas.vue";
import VisaoGeralGrafico from "../components/visaoGeral/VisaoGeralGrafico.vue";
import VisaoGeralNumeros from "../components/visaoGeral/VisaoGeralNumeros.vue";
import VisaoGeralSaidas from "../components/visaoGeral/VisaoGeralSaidas.vue";
import { useAutoRefresh } from "../composables/useAutoRefresh";
import { useVisaoGeral } from "../composables/useVisaoGeral";

// O placar principal permanece visível até zerado; listas auxiliares só
// aparecem quando o servidor encontra movimento para elas.
const {
  periodo, restaurante, restaurantes, dados, carregando, erro,
  podeEscolherRestaurante, carregar,
} = useVisaoGeral();

const SECOES_OPCIONAIS = ["grafico", "formas_de_pagamento", "caixas_abertos",
  "produtos_vendidos", "baixas_de_estoque"];
const semMovimento = computed(() => {
  const vendas = dados.value.vendas || {};
  const comandas = dados.value.comandas || {};
  const temContagem = Number(vendas.pedidos || 0) + Number(comandas.em_uso || 0) + Number(comandas.pagas || 0) > 0;
  return !temContagem && !SECOES_OPCIONAIS.some((secao) => dados.value[secao]);
});

onMounted(() => {
  carregar();
});
useAutoRefresh(carregar, 60_000);
</script>

<style scoped>
.dashboard-view { display: flex; flex-direction: column; gap: var(--page-section-gap); }
.visao-geral__cabecalho {
  display: flex; align-items: end; justify-content: space-between; gap: 20px;
  padding: 4px 2px 0;
}
.visao-geral__cabecalho span {
  color: var(--brand); font: var(--weight-bold) 11px/1 var(--font-sans); letter-spacing: .12em;
}
.visao-geral__cabecalho h1 {
  margin: 7px 0 4px; color: var(--text-strong); font: var(--weight-bold) 28px/1.1 var(--font-sans);
}
.visao-geral__cabecalho p { margin: 0; color: var(--text-muted); font: var(--weight-medium) 13px/1.5 var(--font-sans); }
.visao-geral__alerta {
  padding: 12px 14px; border-radius: 6px; background: var(--danger-subtle); color: var(--danger);
  font: var(--weight-semibold) 13px/1.3 var(--font-sans);
}
.visao-geral__vazio {
  padding: 32px 16px; border: 1px dashed var(--border); border-radius: 8px; text-align: center;
  color: var(--text-muted); font: var(--weight-medium) 14px/1.4 var(--font-sans);
}
</style>
