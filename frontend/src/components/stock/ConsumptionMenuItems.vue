<template>
  <section class="stock-card">
    <div class="stock-card__head">
      <div>
        <h2>O que sai do estoque</h2>
        <p>Insumo na unidade que preferir (8 kg, 500 g). Produto sai pela ficha técnica, em rendimentos da ficha.</p>
      </div>
      <span v-if="rows.length" class="consumption-count">{{ rows.length }} {{ rows.length === 1 ? "item" : "itens" }}</span>
    </div>

    <div class="stock-grid consumption-add">
      <label class="stock-field">
        <span>Tipo de item</span>
        <Select
          v-model="tipoSelecionado" :options="STOCK_ITEM_TYPES" option-label="label" option-value="value" fluid
          @change="busca = ''; sugestoes = []"
        />
      </label>
      <label class="stock-field consumption-add__search">
        <span>Adicionar {{ tipoAtual.label.toLowerCase() }}</span>
        <AutoComplete
          v-model="busca" :suggestions="sugestoes" option-label="name" placeholder="Digite o nome ou código"
          fluid @complete="buscarItens" @item-select="adicionar"
        />
      </label>
    </div>

    <p v-if="!rows.length" class="stock-empty">Nenhum item no cardápio. Busque acima para adicionar.</p>
    <table v-else class="consumption-table">
      <thead>
        <tr><th>Item</th><th>Quantidade</th><th>Unidade</th><th /></tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="row._key">
          <td>
            <strong>{{ row.nome }}</strong>
            <small>{{ row.tipo === "product" ? "Produto · pela ficha técnica" : "Insumo" }}</small>
          </td>
          <td><InputNumber v-model="row.quantidade" :min="0" :max-fraction-digits="3" placeholder="0" fluid /></td>
          <td>
            <Select
              v-if="row.tipo === 'ingredient'" v-model="row.unidade" :options="unitOptions(row)"
              option-label="label" option-value="value" fluid
            />
            <span v-else class="consumption-unit">rendimentos</span>
          </td>
          <td><Button icon="pi pi-trash" severity="danger" text rounded aria-label="Remover item" @click="rows.splice(index, 1)" /></td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import AutoComplete from "primevue/autocomplete";
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import Select from "primevue/dropdown";

import { api } from "../../services/api";
import { STOCK_ITEM_TYPES, stockItemType } from "../../utils/stockBulkAdjustTypes";

const rows = defineModel({ type: Array, required: true });

// A mesma grandeza converte sozinha (kg ↔ g); de outra grandeza o backend recusa.
const MESMA_GRANDEZA = { kg: ["kg", "g"], g: ["kg", "g"], l: ["l", "ml"], ml: ["l", "ml"] };

const tipoSelecionado = ref("ingredient");
const busca = ref("");
const sugestoes = ref([]);
const tipoAtual = computed(() => stockItemType(tipoSelecionado.value));
const chave = (tipo, id) => `${tipo}:${id}`;

async function buscarItens({ query }) {
  const tipo = tipoAtual.value;
  const params = { search: query, is_active: true, ...(tipo.itemType ? { item_type: tipo.itemType } : {}), page_size: 20 };
  const { data } = await api.get(tipo.endpoint, { params });
  const usados = new Set(rows.value.map((row) => chave(row.tipo, row.ingredient || row.product)));
  sugestoes.value = (data.results || data).filter((item) => !usados.has(chave(tipo.kind, item.id)));
}

function adicionar({ value }) {
  const tipo = tipoAtual.value.kind;
  rows.value.push({
    _key: chave(tipo, value.id), tipo, nome: value.name, unidadeBase: value.unit || "",
    ingredient: tipo === "ingredient" ? String(value.id) : null,
    product: tipo === "product" ? String(value.id) : null,
    quantidade: null, unidade: "",
  });
  busca.value = "";
}

function unitOptions(row) {
  const base = row.unidadeBase;
  const outras = (MESMA_GRANDEZA[base] || []).filter((unit) => unit !== base);
  return [{ value: "", label: base || "do insumo" }, ...outras.map((unit) => ({ value: unit, label: unit }))];
}
</script>

<style scoped>
@import "../../styles/stock-document.css";

.consumption-add { margin-bottom: 16px; }
.consumption-add__search { grid-column: span 3; }
.consumption-count { padding: 4px 10px; border-radius: 999px; background: var(--brand-subtle); color: var(--text-brand); font: var(--weight-bold) 12px/1.4 var(--font-sans); white-space: nowrap; }
.consumption-table { width: 100%; border-collapse: collapse; }
.consumption-table th { padding: 8px; color: var(--text-muted); font-size: 12px; text-align: left; border-bottom: 1px solid var(--border); }
.consumption-table td { padding: 8px; vertical-align: middle; border-bottom: 1px solid var(--border-subtle); }
.consumption-table td:first-child { display: flex; flex-direction: column; gap: 2px; }
.consumption-table th:nth-child(2), .consumption-table th:nth-child(3) { width: 170px; }
.consumption-table th:last-child { width: 48px; }
.consumption-table small, .consumption-unit { color: var(--text-muted); font-size: 12px; }

@media (max-width: 1080px) { .consumption-add__search { grid-column: span 1; } }
</style>
