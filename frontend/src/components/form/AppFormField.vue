<template>
  <div class="appfield" :class="{ 'appfield--full': full, 'appfield--error': !!error, 'appfield--readonly': readonly }">
    <label v-if="label" :for="fieldId" class="appfield__label">
      {{ label }}
      <span v-if="required && !readonly" class="appfield__required" aria-hidden="true">*</span>
    </label>

    <!-- O controle real (PrimeVue) é passado pelo pai. `fieldId` e `invalid`
         são expostos para o slot poder ligar id/aria e o estado de erro. -->
    <slot :field-id="fieldId" :invalid="!!error" />

    <small v-if="help && !error" :id="`${fieldId}-help`" class="appfield__help">{{ help }}</small>
    <small v-if="error" :id="`${fieldId}-error`" class="appfield__error" role="alert">
      <AppIcon name="alert-circle" :size="12" />
      {{ error }}
    </small>
  </div>
</template>

<script setup>
/**
 * Wrapper de campo de formulário (Sprint 0 · STC-005).
 * Padroniza label, obrigatoriedade, texto de ajuda e mensagem de erro por campo.
 * O controle em si (InputText, Dropdown, etc.) vai no slot para não amarrar o
 * wrapper a um tipo específico.
 */
import { computed } from "vue";
import AppIcon from "../AppIcon.vue";

let uid = 0;

const props = defineProps({
  label: { type: String, default: "" },
  /** Nome do campo — também usado como base do id/aria quando presente. */
  name: { type: String, default: "" },
  help: { type: String, default: "" },
  /** Mensagem de erro do backend/validação para este campo. */
  error: { type: String, default: "" },
  required: { type: Boolean, default: false },
  /** Ocupa toda a largura do grid. */
  full: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
});

const fieldId = computed(() => `f-${props.name || `field-${(uid += 1)}`}`);
</script>

<style scoped>
.appfield { display: flex; flex-direction: column; gap: var(--field-label-gap); min-width: 0; }
.appfield--full { grid-column: 1 / -1; }

.appfield__label {
  color: var(--text-strong);
  font: var(--weight-bold) 12.5px/1.2 var(--font-sans);
  letter-spacing: 0.01em;
}
.appfield--error .appfield__label { color: var(--danger-text, #dc2626); }
.appfield--readonly .appfield__label { color: var(--text-muted); }
.appfield__required { color: #ef4444; margin-left: 3px; }

.appfield__help { color: var(--text-muted); font: var(--weight-medium) 12px/1.35 var(--font-sans); }
.appfield__error {
  display: flex; align-items: center; gap: 6px;
  color: #ef4444; font: var(--weight-medium) 12px/1.3 var(--font-sans);
}

/* Estado inválido nos controles PrimeVue dentro do slot */
.appfield--error :deep(.p-inputtext),
.appfield--error :deep(.p-dropdown),
.appfield--error :deep(.p-multiselect),
.appfield--error :deep(.p-textarea) {
  border-color: #ef4444 !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, #ef4444 12%, transparent) !important;
}
</style>
