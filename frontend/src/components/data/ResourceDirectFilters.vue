<template>
  <div
    v-for="field in fields" :key="field.name" class="rpro__inline-filter"
    :class="{ 'rpro__inline-filter--compact': field.compact }"
  >
    <span>{{ field.label }}</span>
    <FilterField
      :field="field" :model-value="values[field.name]" :opcoes="opcoesDoFiltro(field)"
      :placeholder="field.compact ? `${field.label}: Todos` : 'Todos'" @update:model-value="change(field.name, $event)"
    />
  </div>
</template>

<script setup>
import FilterField from "./FilterField.vue";
import { opcoesDoFiltro } from "../../utils/opcoesDoFiltro";

defineProps({
  fields: { type: Array, default: () => [] },
  values: { type: Object, required: true },
});

const emit = defineEmits(["change"]);
const change = (name, value) => emit("change", { name, value });
</script>

<style scoped>
.rpro__inline-filter { display: flex; flex-direction: column; gap: 3px; min-width: 160px; }
.rpro__inline-filter--compact > span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.rpro__inline-filter span {
  color: var(--text-muted); font: var(--weight-bold) 10px/1 var(--font-sans);
  text-transform: uppercase; letter-spacing: var(--tracking-caps);
}
@media (max-width: 900px) { .rpro__inline-filter { width: 100%; flex: none; } }
</style>
