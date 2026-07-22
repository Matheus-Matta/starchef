<template>
  <div class="appgrid" :style="gridStyle">
    <slot />
  </div>
</template>

<script setup>
/**
 * Grid responsivo de campos (Sprint 0 · STC-005).
 * Coloca campos relacionados lado a lado e colapsa para uma coluna em telas
 * pequenas. Use `AppFormField` com `full` para ocupar a linha inteira.
 */
import { computed } from "vue";

const props = defineProps({
  /** Número de colunas em desktop. */
  columns: { type: Number, default: 2 },
});

const gridStyle = computed(() => ({
  "--appgrid-cols": props.columns,
}));
</script>

<style scoped>
.appgrid {
  display: grid;
  grid-template-columns: repeat(var(--appgrid-cols, 2), minmax(0, 1fr));
  gap: var(--field-gap-y) var(--field-gap-x);
}

@media (max-width: 760px) {
  .appgrid { grid-template-columns: 1fr; }
}
</style>
