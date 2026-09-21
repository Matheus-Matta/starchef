<template>
  <Dialog v-model:visible="visible" modal header="Filtros avançados" :style="{ width: 'min(620px, 94vw)' }">
    <div class="rpro__advanced-grid">
      <label v-for="field in fields" :key="field.name">
        <span>{{ field.label }}</span>
        <select v-if="field.options?.length" :value="values[field.name] || ''" @change="change(field.name, $event.target.value)">
          <option value="">Todos</option>
          <option v-for="option in field.options" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <select v-else-if="field.type === 'boolean'" :value="values[field.name] || ''" @change="change(field.name, $event.target.value)">
          <option value="">Todos</option>
          <option value="true">Sim</option>
          <option value="false">Não</option>
        </select>
        <InputText v-else :model-value="values[field.name] || ''" :type="field.type === 'number' || field.type === 'decimal' ? 'number' : 'text'" @update:model-value="change(field.name, $event)" />
      </label>
    </div>
    <template #footer>
      <Button label="Limpar" severity="secondary" outlined @click="$emit('clear')" />
      <Button label="Aplicar filtros" @click="$emit('apply')" />
    </template>
  </Dialog>
</template>

<script setup>
import Dialog from "primevue/dialog";
import InputText from "primevue/inputtext";
import Button from "primevue/button";

defineProps({
  fields: { type: Array, default: () => [] },
  values: { type: Object, required: true },
});
const visible = defineModel({ type: Boolean, default: false });
const emit = defineEmits(["apply", "change", "clear"]);
const change = (name, value) => emit("change", { name, value });
</script>

<style scoped>
.rpro__advanced-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.rpro__advanced-grid label { display: flex; flex-direction: column; gap: 6px; }
.rpro__advanced-grid span { color: var(--text-muted); font: var(--weight-bold) 11px/1 var(--font-sans); }
.rpro__advanced-grid select { min-height: var(--control-h); }
@media (max-width: 720px) { .rpro__advanced-grid { grid-template-columns: 1fr; } }
</style>
