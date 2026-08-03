<template>
  <Calendar
    :model-value="modelValue"
    class="app-date-range"
    selection-mode="range"
    date-format="dd/mm/yy"
    :manual-input="false"
    :show-icon="showIcon"
    icon-display="input"
    :placeholder="placeholder"
    :disabled="disabled"
    :max-date="maxDate"
    show-button-bar
    @update:model-value="updateValue"
  />
</template>

<script setup>
import { onMounted } from "vue";
import Calendar from "primevue/calendar";
import { currentMonthRange } from "../../utils/dateRange";

const props = defineProps({
  modelValue: { type: Array, default: null },
  placeholder: { type: String, default: "Selecione o período" },
  disabled: { type: Boolean, default: false },
  showIcon: { type: Boolean, default: true },
  maxDate: { type: Date, default: null },
});

const emit = defineEmits(["update:modelValue", "change"]);

function updateValue(value) {
  emit("update:modelValue", value);
  // Só confirma quando as duas pontas do intervalo foram escolhidas ou ao limpar.
  if (!value || (value[0] && value[1])) emit("change", value);
}

onMounted(() => {
  if (!props.modelValue?.[0] || !props.modelValue?.[1]) {
    updateValue(currentMonthRange());
  }
});
</script>

<style scoped>
.app-date-range {
  width: min(100%, 290px);
}

.app-date-range :deep(.p-inputtext) {
  width: 100%;
}

@media (max-width: 560px) {
  .app-date-range { width: 100%; max-width: none; }
  .app-date-range :deep(.p-inputtext) { min-height: 42px; font-size: 16px; }
  .app-date-range :deep(.p-datepicker-trigger) { width: 42px; }
}
</style>
