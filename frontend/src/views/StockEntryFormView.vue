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
          <label class="stock-field">
            <span>Local de destino *</span>
            <Select
              v-model="form.location"
              :options="locations"
              option-label="name"
              option-value="id"
              placeholder="Selecione o local"
              :disabled="!editable"
              fluid
            />
          </label>
          <label class="stock-field">
            <span>Data da entrada *</span>
            <InputText v-model="form.effective_date" type="date" :disabled="!editable" fluid />
          </label>
          <label class="stock-field">
            <span>Fornecedor</span>
            <InputText v-model="form.supplier" :disabled="!editable" fluid />
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
          <Button v-if="editable" label="Adicionar insumo" icon="pi pi-plus" outlined size="small" @click="addRow" />
        </div>

        <div v-if="!rows.length" class="stock-empty">
          <i class="pi pi-inbox" />
          <p>Nenhum insumo na entrada ainda.</p>
          <Button v-if="editable" label="Adicionar o primeiro" icon="pi pi-plus" size="small" @click="addRow" />
        </div>

        <div v-for="(row, index) in rows" :key="row._key" class="stock-row">
          <div class="stock-row__index">{{ index + 1 }}</div>
          <div class="stock-row__fields">
            <label class="stock-field stock-field--wide">
              <span>Insumo *</span>
              <Select
                v-model="row.ingredient"
                :options="ingredients"
                option-label="name"
                option-value="id"
                filter
                placeholder="Selecione"
                :disabled="!editable"
                fluid
                @change="onIngredientChange(row)"
              />
            </label>
            <label class="stock-field">
              <span>Embalagens</span>
              <InputNumber v-model="row.package_quantity" :min-fraction-digits="0" :max-fraction-digits="3" :disabled="!editable" fluid />
            </label>
            <label class="stock-field">
              <span>Conteúdo por embalagem</span>
              <InputNumber v-model="row.content_per_package" :min-fraction-digits="0" :max-fraction-digits="3" :disabled="!editable" fluid />
            </label>
            <label class="stock-field">
              <span>Unidade</span>
              <Select
                v-model="row.content_unit"
                :options="unitOptions"
                option-label="label"
                option-value="value"
                :disabled="!editable"
                fluid
              />
            </label>
            <label class="stock-field">
              <span>Custo unitário (R$)</span>
              <InputNumber v-model="row.unit_cost" mode="decimal" :min-fraction-digits="2" :max-fraction-digits="4" :disabled="!editable" fluid />
            </label>
            <label class="stock-field">
              <span>Lote do fornecedor</span>
              <InputText v-model="row.supplier_lot" :disabled="!editable" fluid />
            </label>
            <label class="stock-field">
              <span>Fabricação</span>
              <InputText v-model="row.manufactured_at" type="date" :disabled="!editable" fluid />
            </label>
            <label class="stock-field">
              <span>Validade <em v-if="expiryRequired">*</em></span>
              <InputText v-model="row.expires_at" type="date" :disabled="!editable" fluid />
            </label>
            <label class="stock-field">
              <span>Etiquetas</span>
              <InputNumber v-model="row.label_count" :min="1" :max="99" show-buttons :disabled="!editable" fluid />
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
            @click="rows.splice(index, 1)"
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
import { convertUnit } from "../utils/units";

const props = defineProps({ id: { type: String, default: "" } });

const route = useRoute();
const router = useRouter();
const toast = useToast();
const confirm = useConfirm();
const labelSheet = ref(null);

const loading = ref(true);
const saving = ref(false);
const posting = ref(false);
const loadingLabels = ref(false);
const error = ref("");
const locations = ref([]);
const ingredients = ref([]);
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
  effective_date: today(),
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

function blankRow() {
  return {
    _key: ++rowSeq,
    ingredient: null,
    package_quantity: 1,
    content_per_package: null,
    content_unit: "",
    unit_cost: null,
    supplier_lot: "",
    manufactured_at: "",
    expires_at: "",
    label_count: 1,
    notes: "",
  };
}

function addRow() {
  rows.value.push(blankRow());
}

function ingredientOf(row) {
  return ingredients.value.find((item) => item.id === row.ingredient) || null;
}

/** Ao escolher o insumo, a unidade dele é o palpite mais provável. */
function onIngredientChange(row) {
  const ingredient = ingredientOf(row);
  if (ingredient && !row.content_unit) row.content_unit = ingredient.unit;
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

function today() {
  return new Date().toISOString().slice(0, 10);
}

function formatDate(value) {
  if (!value) return "";
  const [year, month, day] = String(value).split("-");
  return day ? `${day}/${month}/${year}` : value;
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
  const { data } = await api.get(`/stock/entries/${sourceId}/`);
  applyEntry(data);
  // O que nao se copia: a identidade e a situacao do documento antigo. A data
  // volta para hoje — repetir a data copiada lancaria o estoque no passado.
  form.status = "draft";
  form.effective_date = today();
  lots.value = [];
  copiedFrom.value = { effective_date: data.effective_date, document_number: data.document_number };
}

function goBack() {
  router.push({ name: "estoque-entradas" });
}

function toPayload() {
  return {
    location: form.location,
    effective_date: form.effective_date,
    supplier: form.supplier,
    document_number: form.document_number,
    notes: form.notes,
    items: rows.value.map((row) => ({
      ingredient: row.ingredient,
      package_quantity: row.package_quantity || 0,
      content_per_package: row.content_per_package || 0,
      content_unit: row.content_unit || "",
      unit_cost: row.unit_cost || 0,
      supplier_lot: row.supplier_lot || "",
      manufactured_at: row.manufactured_at || null,
      expires_at: row.expires_at || null,
      label_count: row.label_count || 1,
      notes: row.notes || "",
    })),
  };
}

function applyEntry(data) {
  Object.assign(form, {
    location: data.location,
    effective_date: data.effective_date,
    supplier: data.supplier || "",
    document_number: data.document_number || "",
    notes: data.notes || "",
    status: data.status,
  });
  rows.value = (data.items || []).map((item) => ({
    _key: ++rowSeq,
    ingredient: item.ingredient,
    package_quantity: Number(item.package_quantity),
    content_per_package: Number(item.content_per_package),
    content_unit: item.content_unit || "",
    unit_cost: Number(item.unit_cost),
    supplier_lot: item.supplier_lot || "",
    manufactured_at: item.manufactured_at || "",
    expires_at: item.expires_at || "",
    label_count: item.label_count || 1,
    notes: item.notes || "",
  }));
  lots.value = (data.items || []).flatMap((item) =>
    (item.lots || []).map((lot) => ({ ...lot, ingredient_name: item.ingredient_name })),
  );
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
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
    error.value = normalizeApiError(err).message;
  } finally {
    saving.value = false;
  }
}

function confirmPost() {
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
  posting.value = true;
  error.value = "";
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
    error.value = normalizeApiError(err).message;
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

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [locationsResponse, ingredientsResponse, settingsResponse] = await Promise.all([
      api.get("/stock/locations/", { params: { is_active: true, page_size: 200 } }),
      api.get("/menu/ingredients/", { params: { is_active: true, page_size: 500 } }),
      api.get("/stock/settings/current/"),
    ]);
    locations.value = locationsResponse.data.results || locationsResponse.data;
    ingredients.value = ingredientsResponse.data.results || ingredientsResponse.data;
    expiryRequired.value = !!settingsResponse.data?.expiry_control_enabled;
    if (!form.location && settingsResponse.data?.default_location) {
      form.location = settingsResponse.data.default_location;
    }

    if (entryId.value) {
      const { data } = await api.get(`/stock/entries/${entryId.value}/`);
      applyEntry(data);
    } else if (copyRequest.value) {
      await applyCopy();
    } else {
      addRow();
    }
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
@import "../styles/stock-document.css";

.stock-doc__alert--info { border-color: var(--info); background: var(--info-subtle); color: var(--info-text); }
</style>
