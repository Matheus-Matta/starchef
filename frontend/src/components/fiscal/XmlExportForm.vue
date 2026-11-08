<template>
  <form class="xml-export-form" @submit.prevent="submit">
    <div class="xml-export-form__field">
      <label for="xml-export-period">Período da emissão</label>
      <AppDateRange id="xml-export-period" v-model="period" />
      <small>Até 366 dias por exportação.</small>
    </div>

    <fieldset class="xml-export-form__field">
      <legend>Situação das notas</legend>
      <div class="xml-export-form__checks">
        <label v-for="option in STATUS_OPTIONS" :key="option.value" class="xml-export-form__check">
          <Checkbox v-model="statuses" :value="option.value" /> {{ option.label }}
        </label>
      </div>
      <small>Autorizadas e canceladas são o que o contador escritura.</small>
    </fieldset>

    <div class="xml-export-form__row">
      <div class="xml-export-form__field">
        <label for="xml-export-model">Modelo</label>
        <Dropdown id="xml-export-model" v-model="documentModel" :options="MODEL_OPTIONS" option-label="label" option-value="value" />
      </div>
      <div class="xml-export-form__field">
        <label for="xml-export-restaurant">Restaurante</label>
        <Dropdown id="xml-export-restaurant" v-model="restaurant" :options="restaurantOptions" option-label="label" option-value="value" />
      </div>
    </div>

    <Message v-if="invalid" severity="warn" :closable="false">{{ invalid }}</Message>
    <div class="xml-export-form__actions">
      <Button type="submit" label="Gerar ZIP" icon="pi pi-file-export" :loading="loading" :disabled="!!invalid" />
    </div>
  </form>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import Button from "primevue/button";
import Checkbox from "primevue/checkbox";
import Dropdown from "primevue/dropdown";
import Message from "primevue/message";

import AppDateRange from "../form/AppDateRange.vue";
import { api } from "../../services/api";
import { currentMonthRange } from "../../utils/dateRange";

defineProps({ loading: { type: Boolean, default: false } });
const emit = defineEmits(["submit"]);

const STATUS_OPTIONS = [
  { value: "issued", label: "Autorizadas" },
  { value: "cancelled", label: "Canceladas" },
  { value: "pending", label: "Pendentes (contingência)" },
  { value: "error", label: "Com erro" },
];
const MODEL_OPTIONS = [
  { value: "", label: "NFC-e e NF-e" },
  { value: "65", label: "Só NFC-e (modelo 65)" },
  { value: "55", label: "Só NF-e (modelo 55)" },
];

const period = ref(currentMonthRange());
const statuses = ref(["issued", "cancelled"]);
const documentModel = ref("");
const restaurant = ref("");
const restaurants = ref([]);
const restaurantOptions = computed(() => [
  { value: "", label: "Todos os restaurantes" },
  ...restaurants.value.map((item) => ({ value: item.id, label: item.name || item.trade_name })),
]);

const invalid = computed(() => {
  if (!period.value?.[0] || !period.value?.[1]) return "Escolha o período: a data inicial e a final.";
  if (!statuses.value.length) return "Marque ao menos uma situação.";
  return "";
});

/** AAAA-MM-DD no fuso do navegador: `toISOString` voltaria um dia à noite. */
function isoDate(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function submit() {
  if (invalid.value) return;
  emit("submit", {
    date_from: isoDate(period.value[0]),
    date_to: isoDate(period.value[1]),
    status: statuses.value,
    ...(documentModel.value ? { document_model: documentModel.value } : {}),
    ...(restaurant.value ? { restaurant: restaurant.value } : {}),
  });
}

onMounted(async () => {
  try {
    const { data } = await api.get("/restaurants/", { params: { page_size: 300 } });
    restaurants.value = data.results || data;
  } catch {
    // Sem a lista, a exportação segue para todos os restaurantes visíveis.
  }
});
</script>

<style scoped>
.xml-export-form { display: flex; flex-direction: column; gap: 18px; }
.xml-export-form__field { display: flex; flex-direction: column; gap: 6px; min-width: 0; border: 0; margin: 0; padding: 0; }
.xml-export-form__field label, .xml-export-form__field legend { color: var(--text-strong); font: var(--weight-semibold) 13px/1.3 var(--font-sans); padding: 0; }
.xml-export-form__field small { color: var(--text-muted); }
.xml-export-form__row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
.xml-export-form__checks { display: flex; flex-wrap: wrap; gap: 10px 20px; }
.xml-export-form__check { display: inline-flex; align-items: center; gap: 8px; color: var(--text-body); font-weight: var(--weight-medium) !important; cursor: pointer; }
.xml-export-form__actions { display: flex; justify-content: flex-end; }
</style>
