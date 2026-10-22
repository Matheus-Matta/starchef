<template>
  <Card v-if="produtos.length" title="Produtos vendidos" subtitle="Os que mais faturaram no período" padding="none">
    <div class="vg-tabela">
      <table>
        <thead>
          <tr><th>Produto</th><th class="vg-num">Qtd.</th><th class="vg-num">Pedidos</th><th class="vg-num">Valor</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in produtos" :key="item.produto">
            <td class="vg-forte">{{ item.produto }}</td>
            <td class="vg-num">{{ quantidade(item.quantidade) }}</td>
            <td class="vg-num">{{ item.pedidos }}</td>
            <td class="vg-num vg-forte">{{ dinheiro(item.valor) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </Card>

  <Card v-if="baixas.length" title="Saídas de estoque" subtitle="Venda, produção, perda e quebra no período" padding="none">
    <div class="vg-tabela">
      <table>
        <thead>
          <tr><th>Item</th><th>Motivo</th><th class="vg-num">Quantidade</th><th v-if="temCusto" class="vg-num">Custo</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in baixas" :key="`${item.item}-${item.tipo}`">
            <td class="vg-forte">{{ item.item }}</td>
            <td>{{ motivo(item.tipo) }}</td>
            <td class="vg-num">{{ quantidade(item.quantidade) }} {{ item.unidade }}</td>
            <td v-if="temCusto" class="vg-num">{{ Number(item.custo) ? dinheiro(item.custo) : "—" }}</td>
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

const props = defineProps({
  produtos: { type: Array, default: () => [] },
  baixas: { type: Array, default: () => [] },
});

const dinheiro = formatMoney;
const temCusto = computed(() => props.baixas.some((b) => Number(b.custo)));

const MOTIVOS = {
  SALE_OUTPUT: "Venda", sale: "Venda", out: "Saída", PRODUCTION_CONSUMPTION: "Produção",
  LOSS: "Perda", BREAKAGE: "Quebra", EXPIRATION: "Validade", TRANSFER_OUT: "Transferência",
  RETURN_TO_SUPPLIER: "Devolução", INVENTORY_ADJUSTMENT_NEGATIVE: "Ajuste de inventário",
  ASSET_DISPOSAL: "Baixa de patrimônio", adjustment: "Ajuste",
};
const motivo = (tipo) => MOTIVOS[tipo] || "Saída";

function quantidade(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", { maximumFractionDigits: 3 });
}
</script>

<style scoped src="./tabela.css"></style>
