<template>
  <div class="stock-doc">
    <header class="stock-doc__head">
      <div>
        <span class="stock-doc__eyebrow">ESTOQUE</span>
        <h1>{{ isNew ? "Nova entrada" : `Entrada ${form.document_number || ""}` }}</h1>
        <p>Cadastre vários insumos de uma vez. Os lotes e as etiquetas nascem da confirmação.</p>
      </div>
      <div class="stock-doc__head-actions">
        <Tag v-if="!isNew" :value="statusLabel" :severity="statusSeverity" rounded />
        <Button label="Voltar" icon="pi pi-arrow-left" text @click="goBack" />
        <Button
          v-if="editable"
          label="Salvar rascunho"
          icon="pi pi-save"
          outlined
          :loading="saving"
          @click="save"
        />
        <Button
          v-if="editable"
          label="Confirmar entrada"
          icon="pi pi-check"
          :loading="posting"
          :disabled="!rows.length"
          @click="confirmPost"
        />
        <Button
          v-if="isPosted"
          label="Imprimir etiquetas"
          icon="pi pi-print"
          :loading="loadingLabels"
          @click="openLabels"
        />
        <Button
          v-if="isPosted"
          label="Cancelar entrada"
          icon="pi pi-times"
          severity="danger"
          text
          @click="confirmCancel"
        />
      </div>
    </header>

    <div v-if="error" class="stock-doc__alert"><i class="pi pi-exclamation-triangle" /> {{ error }}</div>

    <div v-if="copiedFrom" class="stock-doc__alert stock-doc__alert--info">
      <i class="pi pi-copy" />
      <span>
        Cópia da entrada de {{ formatDate(copiedFrom.effective_date) }}<template v-if="copiedFrom.document_number"> (documento {{ copiedFrom.document_number }})</template>.
        A data já está a de hoje; confira o número do documento, os lotes, as validades e os custos antes de confirmar.
      </span>
    </div>

    <div v-if="loading" class="stock-card"><Skeleton height="220px" /></div>

    <template v-else>
      <section class="stock-card">
        <h2>Documento</h2>
        <div class="stock-grid">
          <!-- O armazém é o ponto de partida: é ele que diz onde o
               estoque entra, e de qual restaurante é a entrada. -->
          <label class="stock-field" :class="{ 'stock-field--error': formFieldError('location') }">
            <span>Armazém de destino *</span>
            <Select
              v-model="form.location"
              :options="locationOptions"
              option-label="label"
              option-value="id"
              placeholder="Selecione o armazém"
              :disabled="!editable"
              :loading="loadingContext"
              :class="{ 'p-invalid': formFieldError('location') }"
              filter
              fluid
              @change="onLocationChange"
            />
            <small v-if="formFieldError('location')" class="stock-field__error" role="alert">
              {{ formFieldError("location") }}
            </small>
          </label>
          <label class="stock-field" :class="{ 'stock-field--error': formFieldError('effective_date') }">
            <span>Data da entrada *</span>
            <Calendar
              v-model="form.effective_date"
              class="stock-datepicker"
              date-format="dd/mm/yy"
              :manual-input="false"
              show-icon
              icon-display="input"
              show-button-bar
              :disabled="!editable"
              :class="{ 'p-invalid': formFieldError('effective_date') }"
              @update:model-value="clearFormError('effective_date')"
            />
            <small v-if="formFieldError('effective_date')" class="stock-field__error" role="alert">
              {{ formFieldError("effective_date") }}
            </small>
          </label>
          <label class="stock-field">
            <span>Fornecedor(es)</span>
            <InputText :model-value="supplierSummary" disabled placeholder="Definido em cada insumo" fluid />
          </label>
          <label class="stock-field">
            <span>Nota / documento</span>
            <InputText v-model="form.document_number" :disabled="!editable" fluid />
          </label>
          <label class="stock-field stock-field--full">
            <span>Observações</span>
            <Textarea v-model="form.notes" rows="2" :disabled="!editable" fluid />
          </label>
        </div>
      </section>

      <section class="stock-card">
        <div class="stock-card__head">
          <div>
            <h2>Insumos recebidos</h2>
            <p>
              Uma linha por insumo, lote e validade — é o que define cada lote físico e cada etiqueta.
              <template v-if="expiryRequired"> Esta filial exige validade em toda linha.</template>
            </p>
          </div>
          <Button v-if="editable" label="Adicionar insumo" icon="pi pi-plus" outlined size="small" :disabled="!form.location" @click="addRow" />
        </div>

        <div v-if="!rows.length" class="stock-empty">
          <i class="pi pi-inbox" />
          <p>Nenhum insumo na entrada ainda.</p>
          <Button v-if="editable" label="Adicionar o primeiro" icon="pi pi-plus" size="small" :disabled="!form.location" @click="addRow" />
        </div>

        <div v-for="(row, index) in rows" :key="row._key" class="stock-row">
          <div class="stock-row__index">{{ index + 1 }}</div>
          <div class="stock-row__fields">
            <label class="stock-field stock-field--wide" :class="{ 'stock-field--error': rowFieldError(row, 'ingredient') }">
              <span>Insumo *</span>
              <Select
                v-model="row.ingredient"
                :options="ingredients"
                option-label="name"
                option-value="id"
                filter
                placeholder="Selecione"
                :disabled="!editable"
                :loading="loadingContext"
                :class="{ 'p-invalid': rowFieldError(row, 'ingredient') }"
                fluid
                @change="onIngredientChange(row)"
              />
              <small v-if="rowFieldError(row, 'ingredient')" class="stock-field__error" role="alert">
                {{ rowFieldError(row, "ingredient") }}
              </small>
            </label>
            <label class="stock-field stock-field--wide">
              <span>Fornecedor</span>
              <Select
                v-model="row.supplier"
                :options="suppliers"
                option-label="name"
                option-value="id"
                filter
                show-clear
                placeholder="Sem fornecedor"
                :disabled="!editable"
                fluid
              />
            </label>
            <label class="stock-field" :class="{ 'stock-field--error': rowFieldError(row, 'package_quantity') }">
              <span>Embalagens *</span>
              <InputNumber
                v-model="row.package_quantity"
                :min="0.001"
                :min-fraction-digits="0"
                :max-fraction-digits="3"
                :disabled="!editable"
                :class="{ 'p-invalid': rowFieldError(row, 'package_quantity') }"
                fluid
                @update:model-value="clearRowError(row, 'package_quantity')"
              />
              <small v-if="rowFieldError(row, 'package_quantity')" class="stock-field__error" role="alert">
                {{ rowFieldError(row, "package_quantity") }}
              </small>
            </label>
            <label class="stock-field" :class="{ 'stock-field--error': rowFieldError(row, 'content_per_package') }">
              <span>Conteúdo por embalagem *</span>
              <InputNumber
                v-model="row.content_per_package"
                :min="0.001"
                :min-fraction-digits="0"
                :max-fraction-digits="3"
                :disabled="!editable"
                :class="{ 'p-invalid': rowFieldError(row, 'content_per_package') }"
                fluid
                @update:model-value="clearRowError(row, 'content_per_package')"
              />
              <small>Ex.: pacote de 1 kg = conteúdo 1 e unidade kg.</small>
              <small v-if="rowFieldError(row, 'content_per_package')" class="stock-field__error" role="alert">
                {{ rowFieldError(row, "content_per_package") }}
              </small>
            </label>
            <label class="stock-field" :class="{ 'stock-field--error': rowFieldError(row, 'content_unit') }">
              <span>Unidade *</span>
              <Select
                v-model="row.content_unit"
                :options="unitOptions"
                option-label="label"
                option-value="value"
                :disabled="!editable"
                :class="{ 'p-invalid': rowFieldError(row, 'content_unit') }"
                fluid
                @change="clearRowError(row, 'content_unit')"
              />
              <small v-if="rowFieldError(row, 'content_unit')" class="stock-field__error" role="alert">
                {{ rowFieldError(row, "content_unit") }}
              </small>
            </label>
            <label class="stock-field">
              <span>Custo unitário (R$)</span>
              <InputNumber v-model="row.unit_cost" mode="decimal" :min-fraction-digits="2" :max-fraction-digits="4" :disabled="!editable" fluid />
            </label>
            <label class="stock-field">
              <span>Lote do fornecedor</span>
              <InputText v-model="row.supplier_lot" :disabled="!editable" fluid />
            </label>
            <label class="stock-field" :class="{ 'stock-field--error': rowFieldError(row, 'manufactured_at') }">
              <span>Fabricação</span>
              <Calendar
                v-model="row.manufactured_at"
                class="stock-datepicker"
                date-format="dd/mm/yy"
                :manual-input="false"
                show-icon
                icon-display="input"
                show-button-bar
                :disabled="!editable"
                :class="{ 'p-invalid': rowFieldError(row, 'manufactured_at') }"
                @update:model-value="clearRowError(row, 'manufactured_at')"
              />
              <small v-if="rowFieldError(row, 'manufactured_at')" class="stock-field__error" role="alert">
                {{ rowFieldError(row, "manufactured_at") }}
              </small>
            </label>
            <label class="stock-field" :class="{ 'stock-field--error': rowFieldError(row, 'expires_at') }">
              <span>Validade <em v-if="expiryRequired">*</em></span>
              <Calendar
                v-model="row.expires_at"
                class="stock-datepicker"
                date-format="dd/mm/yy"
                :manual-input="false"
                show-icon
                icon-display="input"
                show-button-bar
                :disabled="!editable"
                :class="{ 'p-invalid': rowFieldError(row, 'expires_at') }"
                @update:model-value="clearRowError(row, 'expires_at')"
              />
              <small v-if="rowFieldError(row, 'expires_at')" class="stock-field__error" role="alert">
                {{ rowFieldError(row, "expires_at") }}
              </small>
            </label>
            <label class="stock-field" :class="{ 'stock-field--error': rowFieldError(row, 'label_count') }">
              <span>Etiquetas</span>
              <InputNumber
                v-model="row.label_count"
                :min="1"
                :max="99"
                show-buttons
                :disabled="!editable"
                :class="{ 'p-invalid': rowFieldError(row, 'label_count') }"
                fluid
                @update:model-value="clearRowError(row, 'label_count')"
              />
              <small v-if="rowFieldError(row, 'label_count')" class="stock-field__error" role="alert">
                {{ rowFieldError(row, "label_count") }}
              </small>
            </label>
            <div class="stock-field stock-row__total">
              <span>Vai para o estoque</span>
              <strong>{{ baseQuantityLabel(row) }}</strong>
            </div>
          </div>
          <Button
            v-if="editable"
            class="stock-row__remove"
            icon="pi pi-trash"
            severity="danger"
            text
            rounded
            aria-label="Remover linha"
            @click="removeRow(index)"
          />
        </div>
      </section>

      <section v-if="isPosted && lots.length" class="stock-card">
        <h2>Lotes gerados</h2>
        <DataTable :value="lots" size="small" class="stock-table">
          <Column field="code" header="Lote" />
          <Column field="ingredient_name" header="Insumo" />
          <Column field="quantity" header="Saldo" />
          <Column field="expires_at" header="Validade" />
        </DataTable>
      </section>
    </template>

    <StockLabelSheet ref="labelSheet" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Calendar from "primevue/calendar";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import Select from "primevue/dropdown";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import Textarea from "primevue/textarea";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import StockLabelSheet from "../components/stock/StockLabelSheet.vue";
import { UNIT_OPTIONS } from "../config/enums";
import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";
import {
  parseApiDate,
  stockEntryApiErrors,
  toApiDate,
  validateStockEntry,
} from "../utils/stockEntryForm";
import { convertUnit } from "../utils/units";

const props = defineProps({ id: { type: String, default: "" } });

const route = useRoute();
const router = useRouter();
const toast = useToast();
const confirm = useConfirm();
const labelSheet = ref(null);

const loading = ref(true);
const loadingContext = ref(false);
const saving = ref(false);
const posting = ref(false);
const loadingLabels = ref(false);
const error = ref("");
const formErrors = ref({});
const rowErrors = ref({});
/** "Depósito central — Unidade Centro": a lista mistura toda a conta. */
const locationOptions = computed(() =>
  locations.value.map((location) => ({
    id: location.id,
    label: location.restaurant_name
      ? `${location.name} — ${location.restaurant_name}`
      : location.name,
  })),
);
const locations = ref([]);
const ingredients = ref([]);
const suppliers = ref([]);
const lots = ref([]);
const expiryRequired = ref(false);
const unitOptions = UNIT_OPTIONS;

const entryId = computed(() => props.id || route.params.id || "");
const isNew = computed(() => !entryId.value);
// `?copy=last` (botao da listagem) ou `?copy=<id>` (duplicar uma entrada).
const copyRequest = computed(() => String(route.query.copy || ""));
const copiedFrom = ref(null);

const form = reactive({
  location: null,
  effective_date: todayDate(),
  supplier: "",
  document_number: "",
  notes: "",
  status: "draft",
});

/** Linhas do documento. `_key` é só para o `v-for` — o backend nunca o vê. */
const rows = ref([]);
let rowSeq = 0;

const editable = computed(() => form.status === "draft");
const isPosted = computed(() => form.status === "posted");
const statusLabel = computed(
  () => ({ draft: "Rascunho", posted: "Confirmada", cancelled: "Cancelada" })[form.status] || form.status,
);
const statusSeverity = computed(
  () => ({ draft: "warning", posted: "success", cancelled: "danger" })[form.status] || "info",
);
const supplierSummary = computed(() => {
  const names = [...new Set(
    rows.value
      .map((row) => suppliers.value.find((supplier) => supplier.id === row.supplier)?.name)
      .filter(Boolean),
  )];
  return names.join(", ") || form.supplier || "";
});

function blankRow() {
  return {
    _key: ++rowSeq,
    ingredient: null,
    supplier: null,
    package_quantity: 1,
    content_per_package: null,
    content_unit: "",
    unit_cost: null,
    supplier_lot: "",
    manufactured_at: null,
    expires_at: null,
    label_count: 1,
    notes: "",
  };
}

function addRow() {
  rows.value.push(blankRow());
}

function removeRow(index) {
  const [removed] = rows.value.splice(index, 1);
  if (removed) {
    const next = { ...rowErrors.value };
    delete next[String(removed._key)];
    rowErrors.value = next;
  }
}

function ingredientOf(row) {
  return ingredients.value.find((item) => item.id === row.ingredient) || null;
}

function formFieldError(field) {
  return formErrors.value[field] || "";
}

function rowFieldError(row, field) {
  return rowErrors.value[String(row._key)]?.[field] || "";
}

function clearFormError(field) {
  if (!formErrors.value[field]) return;
  const next = { ...formErrors.value };
  delete next[field];
  formErrors.value = next;
}

function clearRowError(row, field) {
  const key = String(row._key);
  if (!rowErrors.value[key]?.[field]) return;
  const nextForRow = { ...rowErrors.value[key] };
  delete nextForRow[field];
  const next = { ...rowErrors.value };
  if (Object.keys(nextForRow).length) next[key] = nextForRow;
  else delete next[key];
  rowErrors.value = next;
}

function clearValidationErrors() {
  formErrors.value = {};
  rowErrors.value = {};
}

function validateBeforeSubmit({ forPosting = false } = {}) {
  const validation = validateStockEntry({
    form,
    rows: rows.value,
    expiryRequired: expiryRequired.value,
    forPosting,
  });
  formErrors.value = validation.formErrors;
  rowErrors.value = validation.rowErrors;
  if (!validation.valid) error.value = validation.message;
  return validation.valid;
}

function applyRequestError(err) {
  const normalized = normalizeApiError(err);
  const fields = stockEntryApiErrors(err, rows.value);
  if (fields.hasFieldErrors) {
    formErrors.value = fields.formErrors;
    rowErrors.value = fields.rowErrors;
    error.value = fields.message;
    return;
  }
  error.value = normalized.message;
}

/** Ao escolher o insumo, traz os dados padrão usados no recebimento. */
function onIngredientChange(row) {
  clearRowError(row, "ingredient");
  const ingredient = ingredientOf(row);
  if (!ingredient) return;
  row.content_unit = ingredient.unit;
  row.supplier = ingredient.supplier || null;
  if ((row.unit_cost === null || Number(row.unit_cost) === 0) && Number(ingredient.average_cost) > 0) {
    row.unit_cost = Number(ingredient.average_cost);
  }
}

/**
 * Prévia do que a linha vai somar ao saldo, na unidade do insumo.
 *
 * O cálculo definitivo é do backend — mas mostrar aqui evita o erro clássico
 * de digitar 5 achando "5 kg" quando o insumo está cadastrado em gramas e só
 * descobrir depois de confirmar.
 */
function baseQuantityLabel(row) {
  const ingredient = ingredientOf(row);
  if (!ingredient) return "—";
  const total = Number(row.package_quantity || 0) * Number(row.content_per_package || 0);
  if (!total) return "—";
  const converted = convertUnit(total, row.content_unit || ingredient.unit, ingredient.unit);
  if (converted === null) return "unidade incompatível";
  return `${converted.toLocaleString("pt-BR", { maximumFractionDigits: 3 })} ${ingredient.unit}`;
}

function todayDate() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function formatDate(value) {
  if (!value) return "";
  const date = value instanceof Date ? value : parseApiDate(value);
  return date ? date.toLocaleDateString("pt-BR") : String(value);
}

/**
 * Ultima entrada que serve de modelo.
 *
 * A listagem ja vem da mais recente para a mais antiga; o que se pula e a
 * cancelada — copiar justamente o documento que alguem desfez e o oposto do
 * que o botao promete. Se so houver canceladas, a mais recente ainda e um
 * ponto de partida melhor do que uma tela em branco.
 */
async function findLastEntryId() {
  const { data } = await api.get("/stock/entries/", { params: { page_size: 5 } });
  const list = data.results || data || [];
  return (list.find((item) => item.status !== "cancelled") || list[0])?.id || "";
}

/** Abre a tela com os dados de outra entrada, como rascunho novo. */
async function applyCopy() {
  const sourceId = copyRequest.value === "last" ? await findLastEntryId() : copyRequest.value;
  if (!sourceId) {
    toast.add({ severity: "info", summary: "Nao ha entrada anterior para copiar", life: 4000 });
    addRow();
    return;
  }
  const { data } = await api.get(`/stock/entries/${sourceId}/`, { skipRestaurantScope: true });
  applyEntry(data);
  // O que nao se copia: a identidade e a situacao do documento antigo. A data
  // volta para hoje — repetir a data copiada lancaria o estoque no passado.
  form.status = "draft";
  form.effective_date = todayDate();
  lots.value = [];
  copiedFrom.value = { effective_date: data.effective_date, document_number: data.document_number };
}

function goBack() {
  router.push({ name: "estoque-entradas" });
}

function toPayload() {
  return {
    location: form.location,
    effective_date: toApiDate(form.effective_date),
    supplier: supplierSummary.value,
    document_number: form.document_number,
    notes: form.notes,
    items: rows.value.map((row) => ({
      ingredient: row.ingredient,
      supplier: row.supplier || null,
      package_quantity: row.package_quantity || 0,
      content_per_package: row.content_per_package || 0,
      content_unit: row.content_unit || "",
      unit_cost: row.unit_cost || 0,
      supplier_lot: row.supplier_lot || "",
      manufactured_at: toApiDate(row.manufactured_at),
      expires_at: toApiDate(row.expires_at),
      label_count: row.label_count || 1,
      notes: row.notes || "",
    })),
  };
}

function applyEntry(data) {
  Object.assign(form, {
    location: data.location,
    effective_date: parseApiDate(data.effective_date),
    supplier: data.supplier || "",
    document_number: data.document_number || "",
    notes: data.notes || "",
    status: data.status,
  });
  rows.value = (data.items || []).map((item) => ({
    _key: ++rowSeq,
    ingredient: item.ingredient,
    supplier: item.supplier || null,
    package_quantity: Number(item.package_quantity),
    content_per_package: Number(item.content_per_package),
    content_unit: item.content_unit || "",
    unit_cost: Number(item.unit_cost),
    supplier_lot: item.supplier_lot || "",
    manufactured_at: parseApiDate(item.manufactured_at),
    expires_at: parseApiDate(item.expires_at),
    label_count: item.label_count || 1,
    notes: item.notes || "",
  }));
  lots.value = (data.items || []).flatMap((item) =>
    (item.lots || []).map((lot) => ({ ...lot, ingredient_name: item.ingredient_name })),
  );
}

async function save() {
  if (saving.value) return;
  error.value = "";
  clearValidationErrors();
  if (!validateBeforeSubmit()) return;
  saving.value = true;
  try {
    const payload = toPayload();
    const { data } = entryId.value
      ? await api.patch(`/stock/entries/${entryId.value}/`, payload)
      : await api.post("/stock/entries/", payload);
    applyEntry(data);
    toast.add({ severity: "success", summary: "Rascunho salvo", life: 2500 });
    if (!entryId.value) {
      router.replace({ name: "estoque-entrada-documento", params: { id: data.id } });
    }
  } catch (err) {
    applyRequestError(err);
  } finally {
    saving.value = false;
  }
}

function confirmPost() {
  error.value = "";
  clearValidationErrors();
  if (!validateBeforeSubmit({ forPosting: true })) return;
  confirm.require({
    header: "Confirmar a entrada?",
    message:
      "Os lotes serão criados e o saldo entra no estoque. Uma entrada confirmada não pode mais ser editada.",
    icon: "pi pi-exclamation-triangle",
    acceptLabel: "Confirmar entrada",
    rejectLabel: "Voltar",
    accept: post,
  });
}

async function post() {
  if (posting.value) return;
  error.value = "";
  clearValidationErrors();
  if (!validateBeforeSubmit({ forPosting: true })) return;
  posting.value = true;
  try {
    // Salva antes: o operador pode ter mexido nas linhas sem salvar, e
    // confirmar o que está na tela é o que ele espera.
    const payload = toPayload();
    const saved = entryId.value
      ? (await api.patch(`/stock/entries/${entryId.value}/`, payload)).data
      : (await api.post("/stock/entries/", payload)).data;
    const { data } = await api.post(`/stock/entries/${saved.id}/post_entry/`, {});
    applyEntry(data.entry);
    lots.value = data.lots || [];
    toast.add({
      severity: "success",
      summary: "Entrada confirmada",
      detail: `${data.lots.length} lote(s) criado(s).`,
      life: 4000,
    });
    if (!entryId.value) {
      router.replace({ name: "estoque-entrada-documento", params: { id: saved.id } });
    }
  } catch (err) {
    applyRequestError(err);
  } finally {
    posting.value = false;
  }
}

function confirmCancel() {
  confirm.require({
    header: "Cancelar a entrada?",
    message: "Os lotes ainda intactos voltam a zero. Lotes já consumidos impedem o cancelamento.",
    icon: "pi pi-exclamation-triangle",
    acceptLabel: "Cancelar entrada",
    rejectLabel: "Voltar",
    acceptClass: "p-button-danger",
    accept: async () => {
      try {
        const { data } = await api.post(`/stock/entries/${entryId.value}/cancel/`, {});
        applyEntry(data);
        toast.add({ severity: "success", summary: "Entrada cancelada", life: 3000 });
      } catch (err) {
        error.value = normalizeApiError(err).message;
      }
    },
  });
}

async function openLabels() {
  loadingLabels.value = true;
  try {
    const { data } = await api.get(`/stock/entries/${entryId.value}/labels/`);
    labelSheet.value?.open(data.labels, data.template);
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    loadingLabels.value = false;
  }
}

/** Armazéns e insumos da CONTA — o insumo não é de unidade nenhuma. */
async function loadContext() {
  loadingContext.value = true;
  try {
    const [locationsResponse, ingredientsResponse] = await Promise.all([
      api.get("/stock/locations/", {
        params: { is_active: true, page_size: 500 },
        skipRestaurantScope: true,
      }),
      api.get("/menu/ingredients/", {
        params: { is_active: true, page_size: 500 },
        skipRestaurantScope: true,
      }),
    ]);
    locations.value = locationsResponse.data.results || locationsResponse.data;
    ingredients.value = ingredientsResponse.data.results || ingredientsResponse.data;
    if (form.location && !locations.value.some((location) => location.id === form.location)) {
      form.location = null;
    }
  } finally {
    loadingContext.value = false;
  }
}

/** As regras de validade são do restaurante — e ele vem do armazém. */
async function loadLocationSettings() {
  const location = locations.value.find((item) => item.id === form.location);
  if (!location?.restaurant) {
    expiryRequired.value = false;
    return;
  }
  try {
    const { data } = await api.get("/stock/settings/current/", {
      params: { restaurant: location.restaurant },
      skipRestaurantScope: true,
    });
    expiryRequired.value = !!data?.expiry_control_enabled;
  } catch {
    // Sem as configurações a entrada continua possível; o controle de
    // validade é que deixa de ser exigido nesta tela — o servidor ainda
    // recusa se for obrigatório.
    expiryRequired.value = false;
  }
}

async function onLocationChange() {
  clearFormError("location");
  error.value = "";
  try {
    await loadLocationSettings();
  } catch (err) {
    applyRequestError(err);
  }
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const suppliersResponse = await api.get("/stock/suppliers/", {
      params: { is_active: true, page_size: 500 },
      skipRestaurantScope: true,
    });
    suppliers.value = suppliersResponse.data.results || suppliersResponse.data;
    await loadContext();

    if (entryId.value) {
      const { data } = await api.get(`/stock/entries/${entryId.value}/`, { skipRestaurantScope: true });
      applyEntry(data);
    } else if (copyRequest.value) {
      await applyCopy();
    }

    if (form.location) await loadLocationSettings();
    if (!rows.value.length) {
      addRow();
    }
  } catch (err) {
    applyRequestError(err);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
@import "../styles/stock-document.css";

.stock-doc__alert--info { border-color: var(--info); background: var(--info-subtle); color: var(--info-text); }
.stock-datepicker { width: 100%; }
.stock-datepicker :deep(.p-inputtext) { width: 100%; }
.stock-field--error > span { color: var(--danger-text); }
.stock-field small.stock-field__error {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--danger-text);
  font-weight: var(--weight-medium);
  line-height: 1.35;
}
.stock-field--error :deep(.p-inputtext),
.stock-field--error :deep(.p-dropdown) {
  border-color: var(--danger-border) !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--danger-text) 12%, transparent) !important;
}
</style>
