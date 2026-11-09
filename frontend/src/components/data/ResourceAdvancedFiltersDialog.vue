<template>
  <Dialog v-model:visible="visible" modal header="Filtros avançados" :style="{ width: 'min(620px, 94vw)' }">
    <div class="filtros-grid">
      <div v-for="field in fields" :key="field.name" class="filtros-campo">
        <label :for="`filtro-${field.name}`">{{ field.label }}</label>
        <FilterField
          :id="`filtro-${field.name}`" :field="field" :model-value="values[field.name]"
          :opcoes="opcoesDoFiltro(field, { colunas: columns, remotas })" :carregando="carregando && ehRemoto(field)"
          @update:model-value="change(field.name, $event)"
        />
      </div>
    </div>
    <template #footer>
      <Button label="Limpar" severity="secondary" outlined @click="$emit('clear')" />
      <Button label="Aplicar filtros" @click="$emit('apply')" />
    </template>
  </Dialog>
</template>

<script setup>
import { ref, watch } from "vue";
import Button from "primevue/button";
import Dialog from "primevue/dialog";

import FilterField from "./FilterField.vue";
import { api } from "../../services/api";
import { loadRemoteOptions } from "../../services/remoteOptions";
import { ehRemoto, opcoesDoFiltro } from "../../utils/opcoesDoFiltro";

const props = defineProps({
  fields: { type: Array, default: () => [] },
  values: { type: Object, required: true },
  // Colunas da lista: um filtro de texto com rótulos na coluna vira lista.
  columns: { type: Array, default: () => [] },
});
const visible = defineModel({ type: Boolean, default: false });
const emit = defineEmits(["apply", "change", "clear"]);
const change = (name, value) => emit("change", { name, value });

// As opções dos cadastros relacionados só são buscadas quando o modal abre,
// e uma vez só: abrir a lista não paga por um modal que talvez nem seja usado.
const remotas = ref({});
const carregando = ref(false);
let buscou = false;
watch(visible, async (aberto) => {
  if (!aberto || buscou || !props.fields.some(ehRemoto)) return;
  buscou = true;
  carregando.value = true;
  try {
    remotas.value = await loadRemoteOptions(props.fields, api.get);
  } finally {
    carregando.value = false;
  }
});
</script>

<style scoped>
.filtros-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.filtros-campo { display: flex; min-width: 0; flex-direction: column; gap: 6px; }
.filtros-campo label { color: var(--text-muted); font: var(--weight-bold) 11px/1 var(--font-sans); }
@media (max-width: 720px) { .filtros-grid { grid-template-columns: 1fr; } }
</style>
