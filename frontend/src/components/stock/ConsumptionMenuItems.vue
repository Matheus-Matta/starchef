<template>
  <section class="stock-card">
    <div class="stock-card__head">
      <div>
        <h2>O que sai do estoque</h2>
        <p>Insumo na unidade que preferir (8 kg, 500 g). Produto sai pela ficha técnica: a quantidade é em rendimentos da ficha.</p>
      </div>
      <Button label="Adicionar item" icon="pi pi-plus" outlined size="small" @click="add" />
    </div>

    <div v-if="!rows.length" class="stock-empty">
      <i class="pi pi-inbox" />
      <p>Nenhum item ainda.</p>
      <Button label="Adicionar o primeiro" icon="pi pi-plus" size="small" @click="add" />
    </div>

    <div v-for="(row, index) in rows" :key="row._key" class="stock-row">
      <div class="stock-row__index">{{ index + 1 }}</div>
      <div class="stock-row__fields">
        <label class="stock-field">
          <span>Tipo</span>
          <Select v-model="row.tipo" :options="TIPOS" option-label="label" option-value="value" fluid @change="limpar(row)" />
        </label>
        <label class="stock-field stock-field--wide">
          <span>{{ row.tipo === "product" ? "Produto *" : "Insumo *" }}</span>
          <Select
            v-if="row.tipo === 'product'" v-model="row.product" :options="products" option-label="name"
            option-value="id" filter placeholder="Selecione o produto" fluid
          />
          <Select
            v-else v-model="row.ingredient" :options="ingredients" option-label="name" option-value="id"
            filter placeholder="Selecione o insumo" fluid
          />
        </label>
        <label class="stock-field">
          <span>Quantidade * <small>{{ unitHint(row) }}</small></span>
          <InputNumber v-model="row.quantidade" :min="0" :min-fraction-digits="0" :max-fraction-digits="3" fluid />
        </label>
        <label v-if="row.tipo === 'ingredient'" class="stock-field">
          <span>Unidade</span>
          <Select v-model="row.unidade" :options="unitOptions(row)" option-label="label" option-value="value" fluid />
        </label>
      </div>
      <Button
        class="stock-row__remove" icon="pi pi-trash" severity="danger" text rounded aria-label="Remover item"
        @click="rows.splice(index, 1)"
      />
    </div>
  </section>
</template>

<script setup>
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import Select from "primevue/dropdown";

const props = defineProps({
  ingredients: { type: Array, default: () => [] },
  products: { type: Array, default: () => [] },
});
const rows = defineModel({ type: Array, required: true });

const TIPOS = [{ value: "ingredient", label: "Insumo" }, { value: "product", label: "Produto" }];
// A mesma grandeza converte sozinha (kg ↔ g); de outra grandeza o backend recusa.
const MESMA_GRANDEZA = { kg: ["kg", "g"], g: ["kg", "g"], l: ["l", "ml"], ml: ["l", "ml"] };

let sequence = 0;
function add() {
  rows.value.push({ _key: `novo-${sequence++}`, tipo: "ingredient", ingredient: null, product: null, quantidade: null, unidade: "" });
}

function limpar(row) {
  row.ingredient = null;
  row.product = null;
  row.unidade = "";
}

function unitOf(row) {
  return props.ingredients.find((item) => item.id === row.ingredient)?.unit || "";
}

function unitOptions(row) {
  const base = unitOf(row);
  const outras = (MESMA_GRANDEZA[base] || []).filter((unit) => unit !== base);
  return [{ value: "", label: base ? `${base} (do insumo)` : "do insumo" }, ...outras.map((unit) => ({ value: unit, label: unit }))];
}

function unitHint(row) {
  if (row.tipo === "product") return "(rendimentos)";
  return `(${row.unidade || unitOf(row) || "unidade do insumo"})`;
}
</script>
