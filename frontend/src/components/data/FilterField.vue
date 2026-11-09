<template>
  <Dropdown
    v-if="tipo === 'lista'" :model-value="texto" :options="opcoes" option-label="label" option-value="value"
    :placeholder="placeholder" :filter="opcoes.length > 8" :loading="carregando" show-clear fluid
    :aria-label="field.label" @update:model-value="emitir"
  />
  <SelectButton
    v-else-if="tipo === 'simnao'" :model-value="texto" :options="SIM_NAO" option-label="label" option-value="value"
    :allow-empty="false" :aria-label="field.label" @update:model-value="emitir"
  />
  <InputNumber
    v-else-if="tipo === 'numero'" :model-value="texto === '' ? null : Number(texto)" :max-fraction-digits="2"
    :aria-label="field.label" fluid @update:model-value="emitir"
  />
  <Calendar
    v-else-if="tipo === 'data'" :model-value="texto ? new Date(`${texto}T00:00:00`) : null" date-format="dd/mm/yy"
    show-icon show-button-bar :aria-label="field.label" fluid @update:model-value="emitir($event ? ymd($event) : '')"
  />
  <InputText v-else :model-value="texto" :aria-label="field.label" fluid @update:model-value="emitir" />
</template>

<script setup>
import { computed } from "vue";
import Calendar from "primevue/calendar";
import Dropdown from "primevue/dropdown";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import SelectButton from "primevue/selectbutton";

import { ymd } from "../../composables/listUrlFields";
import { SEM_FILTRO, tipoDoFiltro } from "../../utils/opcoesDoFiltro";

// Um campo de filtro, sempre com o componente do PrimeVue do tipo dele.
// O valor é sempre TEXTO ("" = sem filtro): ele mora na URL da lista.
const props = defineProps({
  field: { type: Object, required: true },
  modelValue: { type: [String, Number, Boolean], default: SEM_FILTRO },
  opcoes: { type: Array, default: () => [] },
  carregando: { type: Boolean, default: false },
  placeholder: { type: String, default: "Todos" },
});
const emit = defineEmits(["update:modelValue"]);

const SIM_NAO = [{ label: "Todos", value: "" }, { label: "Sim", value: "true" }, { label: "Não", value: "false" }];
const texto = computed(() => (props.modelValue === null || props.modelValue === undefined ? "" : String(props.modelValue)));
const tipo = computed(() => tipoDoFiltro(props.field, props.opcoes));
const emitir = (valor) => emit("update:modelValue", valor === null || valor === undefined ? SEM_FILTRO : String(valor));
</script>
