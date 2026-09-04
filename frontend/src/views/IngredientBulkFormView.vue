<template>
  <div class="stock-doc ingredient-bulk">
    <header class="stock-doc__head">
      <div>
        <span class="stock-doc__eyebrow">CADASTROS</span>
        <h1>Insumos em lote</h1>
        <p>Inclua várias linhas e salve todos os insumos de uma vez.</p>
      </div>
      <div class="stock-doc__head-actions">
        <Button label="Voltar" icon="pi pi-arrow-left" text @click="goBack" />
        <Button label="Salvar insumos" icon="pi pi-check" :loading="saving" :disabled="!validRows.length" @click="save" />
      </div>
    </header>

    <div v-if="error" class="stock-doc__alert">
      <i class="pi pi-exclamation-triangle" /> {{ error }}
    </div>

    <section class="stock-card">
      <div class="stock-card__head">
        <div>
          <h2>Insumos</h2>
          <p>Nome e unidade são obrigatórios. O fornecedor escolhido será sugerido automaticamente nas entradas.</p>
        </div>
        <div class="ingredient-bulk__add-actions">
          <Button label="Adicionar linha" icon="pi pi-plus" outlined size="small" @click="addRows(1)" />
          <Button label="Adicionar 5" icon="pi pi-list" text size="small" @click="addRows(5)" />
        </div>
      </div>

      <div v-for="(row, index) in rows" :key="row._key" class="stock-row ingredient-bulk__row">
        <div class="stock-row__index">{{ index + 1 }}</div>
        <div class="stock-row__fields">
          <label class="stock-field stock-field--wide">
            <span>Nome do insumo *</span>
            <InputText v-model="row.name" placeholder="Ex.: Farinha de trigo" fluid />
          </label>
          <label class="stock-field">
            <span>Unidade *</span>
            <Select v-model="row.unit" :options="unitOptions" option-label="label" option-value="value" fluid />
          </label>
          <label v-if="hasLogistica" class="stock-field stock-field--wide">
            <span>Fornecedor padrão</span>
            <Select
              v-model="row.supplier"
              :options="suppliers"
              option-label="name"
              option-value="id"
              filter
              show-clear
              placeholder="Sem fornecedor"
              fluid
            />
          </label>
          <label v-if="hasLogistica" class="stock-field">
            <span>Estoque mínimo</span>
            <InputNumber v-model="row.minimum_stock" :min="0" :max-fraction-digits="3" fluid />
          </label>
          <label class="ingredient-bulk__active">
            <Checkbox v-model="row.is_active" binary />
            <span>Ativo</span>
          </label>
        </div>
        <Button
          class="stock-row__remove"
          icon="pi pi-trash"
          severity="danger"
          text
          rounded
          aria-label="Remover linha"
          :disabled="rows.length === 1"
          @click="rows.splice(index, 1)"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import Button from "primevue/button";
import Checkbox from "primevue/checkbox";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import Select from "primevue/dropdown";
import { useToast } from "primevue/usetoast";

import { UNIT_OPTIONS } from "../config/enums";
import { api } from "../services/api";
import { useAuthStore } from "../stores/auth";
import { normalizeApiError } from "../utils/apiError";

const router = useRouter();
const toast = useToast();
const auth = useAuthStore();
const saving = ref(false);
const error = ref("");
const suppliers = ref([]);
const rows = ref([]);
const unitOptions = UNIT_OPTIONS;
const hasLogistica = computed(() => auth.hasModule("logistica"));
let rowSeq = 0;

function blankRow() {
  return {
    _key: ++rowSeq,
    name: "",
    unit: "unit",
    supplier: null,
    minimum_stock: null,
    is_active: true,
  };
}

function addRows(count) {
  for (let index = 0; index < count; index += 1) rows.value.push(blankRow());
}

const validRows = computed(() => rows.value.filter((row) => String(row.name || "").trim()));

function goBack() {
  router.push({ name: "ingredientes" });
}

function payloadFor(row) {
  const payload = {
    name: String(row.name).trim(),
    unit: row.unit,
    is_active: row.is_active,
  };
  if (hasLogistica.value) {
    payload.supplier = row.supplier || null;
    payload.minimum_stock = row.minimum_stock ?? null;
  }
  return payload;
}

async function save() {
  if (saving.value || !validRows.value.length) return;
  saving.value = true;
  error.value = "";
  try {
    const { data } = await api.post("/menu/ingredients/bulk/", {
      items: validRows.value.map(payloadFor),
    });
    toast.add({
      severity: "success",
      summary: `${data.length} insumos cadastrados`,
      life: 3500,
    });
    goBack();
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  addRows(3);
  if (!hasLogistica.value) return;
  try {
    const { data } = await api.get("/stock/suppliers/", { params: { is_active: true, page_size: 500 } });
    suppliers.value = data.results || data;
  } catch (err) {
    error.value = normalizeApiError(err).message;
  }
});
</script>

<style scoped>
@import "../styles/stock-document.css";

.ingredient-bulk__add-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.ingredient-bulk__active {
  align-items: center;
  align-self: end;
  display: flex;
  gap: 0.5rem;
  min-height: 2.5rem;
}
</style>
