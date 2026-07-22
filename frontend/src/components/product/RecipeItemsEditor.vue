<template>
  <section class="ritems">
    <div class="ritems__head">
      <h3>Ficha técnica <small>{{ rows.length }} ingredientes</small></h3>
      <Button
        v-if="!readonly"
        label="Adicionar ingrediente"
        icon="pi pi-plus"
        size="small"
        severity="secondary"
        outlined
        @click="openCreate"
      />
    </div>

    <p v-if="!rows.length" class="ritems__empty">
      {{ readonly ? "Nenhum ingrediente cadastrado." : "Nenhum ingrediente ainda. Clique em \"Adicionar ingrediente\"." }}
    </p>

    <ul v-else class="ritems__list">
      <li v-for="row in rows" :key="row.id" class="ritems__item">
        <span class="ritems__name">{{ row.ingredient_name || ingredientLabel(row.ingredient) }}</span>
        <span class="ritems__qty">{{ formatQuantity(row.quantity) }} {{ row.unit }}</span>
        <strong class="ritems__cost">{{ money(row.total_cost) }}</strong>
        <div v-if="!readonly" class="ritems__actions">
          <Button icon="pi pi-pencil" text rounded aria-label="Editar item" @click="openEdit(row)" />
          <Button icon="pi pi-trash" text rounded severity="danger" aria-label="Remover item" @click="confirmRemove(row)" />
        </div>
      </li>
    </ul>

    <div v-if="rows.length" class="ritems__total">
      <span>Custo estimado</span>
      <strong>{{ money(estimatedCost) }}</strong>
    </div>

    <AppEntityDialog
      v-model:visible="dialogOpen"
      entity="ingrediente"
      :mode="editing.id ? 'edit' : 'create'"
      :saving="saving"
      :dirty="dirty"
      width="500px"
      @save="save"
    >
      <AppErrorSummary :message="formError" />
      <AppFormGrid :columns="2">
        <AppFormField label="Ingrediente" name="ingredient" :error="fieldErrors.ingredient" required full>
          <template #default="{ fieldId, invalid }">
            <Dropdown
              :id="fieldId"
              v-model="editing.ingredient"
              :options="ingredientOptions"
              option-label="label"
              option-value="value"
              :class="{ 'p-invalid': invalid }"
              :loading="loadingIngredients"
              placeholder="Buscar ingrediente..."
              filter
              fluid
              @change="onIngredientChange"
            />
          </template>
        </AppFormField>
        <AppFormField label="Quantidade" name="quantity" :error="fieldErrors.quantity" required>
          <template #default="{ fieldId, invalid }">
            <InputNumber :id="fieldId" v-model="editing.quantity" :class="{ 'p-invalid': invalid }" :min="0" :min-fraction-digits="0" :max-fraction-digits="3" @update:model-value="dirty = true" />
          </template>
        </AppFormField>
        <AppFormField label="Unidade" name="unit" :error="fieldErrors.unit" required>
          <template #default="{ fieldId, invalid }">
            <Dropdown :id="fieldId" v-model="editing.unit" :options="UNIT_OPTIONS" option-label="label" option-value="value" :class="{ 'p-invalid': invalid }" placeholder="Unidade" fluid @change="dirty = true" />
          </template>
        </AppFormField>
      </AppFormGrid>
    </AppEntityDialog>
  </section>
</template>

<script setup>
/**
 * Gerencia os ingredientes (itens) de uma receita via modal reutilizável
 * (Sprint 3 · STC-034/035). A busca de ingrediente é filtrável; o custo estimado
 * é recalculado no backend a cada salvamento e refletido aqui.
 *
 * Uso: :key="recipeId" no pai para reiniciar o estado ao trocar de receita.
 */
import { computed, onMounted, ref } from "vue";
import Button from "primevue/button";
import Dropdown from "primevue/dropdown";
import InputNumber from "primevue/inputnumber";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import AppEntityDialog from "../form/AppEntityDialog.vue";
import AppFormGrid from "../form/AppFormGrid.vue";
import AppFormField from "../form/AppFormField.vue";
import AppErrorSummary from "../form/AppErrorSummary.vue";
import { ResourceService } from "../../services/ResourceService";
import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";
import { formatMoney, formatQuantity } from "../../utils/format";
import { UNIT_OPTIONS } from "../../config/enums";

const props = defineProps({
  recipeId: { type: String, required: true },
  initialItems: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
});

const service = new ResourceService({ endpoint: "/menu/recipe-items/" });
const confirm = useConfirm();
const toast = useToast();

const money = formatMoney;

function toRow(item) {
  return {
    id: item.id ?? null,
    ingredient: item.ingredient ?? null,
    ingredient_name: item.ingredient_name ?? "",
    quantity: Number(item.quantity ?? 0),
    unit: item.unit ?? "",
    total_cost: Number(item.total_cost ?? 0),
  };
}

const rows = ref(props.initialItems.map(toRow));
const estimatedCost = computed(() => rows.value.reduce((sum, row) => sum + (Number(row.total_cost) || 0), 0));

/* ── Opções de ingrediente (busca filtrável) ─────────────────────────── */
const ingredientOptions = ref([]);
const loadingIngredients = ref(false);
async function loadIngredients() {
  loadingIngredients.value = true;
  try {
    const res = await api.get("/menu/ingredients/", { params: { page_size: 200, ordering: "name" } });
    const list = res.data.results || res.data || [];
    ingredientOptions.value = list.map((ing) => ({ label: ing.name, value: ing.id, unit: ing.unit }));
  } catch {
    ingredientOptions.value = [];
  } finally {
    loadingIngredients.value = false;
  }
}
function ingredientLabel(id) {
  return ingredientOptions.value.find((o) => o.value === id)?.label || "Ingrediente";
}

/* ── Modal ────────────────────────────────────────────────────────────── */
const dialogOpen = ref(false);
const saving = ref(false);
const dirty = ref(false);
const formError = ref("");
const fieldErrors = ref({});
const editing = ref(emptyForm());

function emptyForm() {
  return { id: null, ingredient: null, quantity: 1, unit: "" };
}
function resetForm(data) {
  editing.value = data ? { id: data.id, ingredient: data.ingredient, quantity: data.quantity, unit: data.unit } : emptyForm();
  formError.value = "";
  fieldErrors.value = {};
  dirty.value = false;
}
function openCreate() {
  resetForm();
  dialogOpen.value = true;
}
function openEdit(row) {
  resetForm(row);
  dialogOpen.value = true;
}

// Ao escolher um ingrediente, herda a unidade padrão dele (se ainda vazia).
function onIngredientChange() {
  dirty.value = true;
  const match = ingredientOptions.value.find((o) => o.value === editing.value.ingredient);
  if (match && !editing.value.unit) editing.value.unit = match.unit;
}

function validateForm() {
  const errors = {};
  if (!editing.value.ingredient) errors.ingredient = "Selecione um ingrediente.";
  if (!editing.value.quantity || Number(editing.value.quantity) <= 0) errors.quantity = "A quantidade deve ser maior que zero.";
  if (!editing.value.unit) errors.unit = "Selecione a unidade.";
  fieldErrors.value = errors;
  return Object.keys(errors).length === 0;
}

async function save() {
  if (!validateForm()) return;
  saving.value = true;
  formError.value = "";
  try {
    const payload = {
      recipe: props.recipeId,
      ingredient: editing.value.ingredient,
      quantity: Number(editing.value.quantity),
      unit: editing.value.unit,
    };
    // restaurante/filial são herdados da receita no backend.
    const saved = editing.value.id ? await service.update(editing.value.id, payload) : await service.create(payload);
    const row = toRow(saved);
    if (!row.ingredient_name) row.ingredient_name = ingredientLabel(row.ingredient);
    upsertRow(row);
    dialogOpen.value = false;
    toast.add({ severity: "success", summary: editing.value.id ? "Ingrediente atualizado" : "Ingrediente adicionado", life: 2000 });
  } catch (err) {
    const normalized = normalizeApiError(err);
    fieldErrors.value = { ...fieldErrors.value, ...normalized.fieldErrors };
    formError.value = normalized.message;
  } finally {
    saving.value = false;
  }
}

function upsertRow(row) {
  const index = rows.value.findIndex((r) => r.id === row.id);
  if (index >= 0) rows.value.splice(index, 1, row);
  else rows.value.push(row);
}

function confirmRemove(row) {
  confirm.require({
    header: "Remover ingrediente?",
    message: `Remover "${row.ingredient_name || ingredientLabel(row.ingredient)}" da ficha técnica?`,
    icon: "pi pi-exclamation-triangle",
    acceptLabel: "Remover",
    rejectLabel: "Cancelar",
    acceptClass: "p-button-danger",
    accept: () => remove(row),
  });
}
async function remove(row) {
  try {
    if (row.id) await service.remove(row.id);
    rows.value = rows.value.filter((r) => r.id !== row.id);
    toast.add({ severity: "success", summary: "Ingrediente removido", life: 2000 });
  } catch (err) {
    toast.add({ severity: "error", summary: "Não foi possível remover", detail: normalizeApiError(err).message, life: 4000 });
  }
}

onMounted(loadIngredients);
</script>

<style scoped>
.ritems { display: flex; flex-direction: column; gap: 12px; padding: 18px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-sm); }
.ritems__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.ritems__head h3 { display: flex; align-items: center; gap: 8px; color: var(--text-strong); font: var(--weight-extra) 14px/1.2 var(--font-sans); }
.ritems__head small { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }
.ritems__empty { color: var(--text-muted); font: var(--weight-medium) 13px/1.5 var(--font-sans); }

.ritems__list { display: flex; flex-direction: column; }
.ritems__item { display: grid; grid-template-columns: minmax(0, 1fr) auto auto auto; align-items: center; gap: 12px; padding: 10px 0; border-top: 1px solid var(--border-subtle); }
.ritems__item:first-child { border-top: none; }
.ritems__name { color: var(--text-strong); font: var(--weight-bold) 13.5px/1.2 var(--font-sans); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ritems__qty { color: var(--text-body); font: var(--weight-semibold) 13px/1 var(--font-sans); white-space: nowrap; }
.ritems__cost { color: var(--success-text); font: var(--weight-bold) 13px/1 var(--font-sans); white-space: nowrap; }
.ritems__actions { display: flex; align-items: center; gap: 2px; }

.ritems__total { display: flex; align-items: center; justify-content: space-between; padding-top: 12px; border-top: 2px solid var(--border); }
.ritems__total span { color: var(--text-muted); font: var(--weight-bold) 12px/1 var(--font-sans); text-transform: uppercase; letter-spacing: var(--tracking-caps); }
.ritems__total strong { color: var(--text-strong); font: var(--weight-extra) 16px/1 var(--font-sans); }

@media (max-width: 760px) {
  .ritems__item { grid-template-columns: 1fr auto; }
}
</style>
