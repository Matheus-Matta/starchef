<template>
  <Card title="Caixas abertos agora" :subtitle="`${dinheiro(totalNasGavetas)} nas gavetas`" padding="none">
    <div class="vg-tabela">
      <table>
        <thead>
          <tr>
            <th>Caixa</th>
            <th>Operador</th>
            <th>Aberto às</th>
            <th v-for="coluna in colunas" :key="coluna.chave" class="vg-num">{{ coluna.rotulo }}</th>
            <th class="vg-num">Na gaveta</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="caixa in caixas" :key="caixa.id">
            <td class="vg-forte">{{ caixa.caixa }}</td>
            <td>{{ caixa.operador || "—" }}</td>
            <td>{{ hora(caixa.aberto_em) }}</td>
            <td v-for="coluna in colunas" :key="coluna.chave" class="vg-num">{{ dinheiro(caixa[coluna.chave]) }}</td>
            <td class="vg-num vg-forte">{{ dinheiro(caixa.saldo) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </Card>
</template>

<script setup>
import { computed } from "vue";

import Card from "../display/Card.vue";
import { formatMoney } from "../../utils/format";

const props = defineProps({ caixas: { type: Array, default: () => [] } });

const dinheiro = (valor) => (Number(valor) ? formatMoney(valor) : "—");

// Coluna que é zero em todos os caixas (ninguém fez sangria) não aparece.
const TODAS = [
  { chave: "abertura", rotulo: "Abertura" },
  { chave: "vendas_em_dinheiro", rotulo: "Vendas em dinheiro" },
  { chave: "suprimentos", rotulo: "Suprimentos" },
  { chave: "sangrias", rotulo: "Sangrias" },
];
const colunas = computed(() => TODAS.filter((c) => props.caixas.some((caixa) => Number(caixa[c.chave]))));
const totalNasGavetas = computed(() => props.caixas.reduce((soma, c) => soma + Number(c.saldo || 0), 0));

function hora(iso) {
  return iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "—";
}
</script>

<style scoped src="./tabela.css"></style>
