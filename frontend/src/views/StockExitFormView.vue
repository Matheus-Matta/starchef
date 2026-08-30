<template>
  <div class="stock-doc">
    <header class="stock-doc__head">
      <div>
        <span class="stock-doc__eyebrow">ESTOQUE</span>
        <h1>{{ isNew ? "Nova saída" : "Saída de estoque" }}</h1>
        <p>Informe os insumos e o motivo. O sistema separa os lotes por {{ strategyLabel }}.</p>
      </div>
      <div class="stock-doc__head-actions">
        <Tag v-if="!isNew" :value="statusLabel" :severity="statusSeverity" rounded />
        <Button label="Voltar" icon="pi pi-arrow-left" text @click="goBack" />
        <Button v-if="editable" label="Salvar rascunho" icon="pi pi-save" outlined :loading="saving" @click="save" />
        <Button
          v-if="editable"
          label="Separar lotes"
          icon="pi pi-sitemap"
          :loading="suggesting"
          :disabled="!rows.length"
          @click="suggest"
        />
        <Button
          v-if="editable && hasAllocations"
          label="Conferir etiquetas"
          icon="pi pi-qrcode"
          outlined
          @click="goToPicking"
        />
        <Button
          v-if="editable && hasAllocations"
          label="Confirmar saída"
          icon="pi pi-check"
          :loading="posting"
          @click="confirmPost"
        />
      </div>
    </header>

    <div v-if="error" class="stock-doc__alert"><i class="pi pi-exclamation-triangle" /> {{ error }}</div>

    <div v-if="shortages.length" class="stock-doc__alert stock-doc__alert--warn">
      <i class="pi pi-exclamation-circle" />
      <span>
        Saldo insuficiente:
        {{ shortages.map((s) => `${s.ingredient_name} (faltam ${s.missing})`).join(" · ") }}
      </span>
    </div>

    <div v-if="loading" class="stock-card"><Skeleton height="220px" /></div>

    <template v-else>
      <section class="stock-card">
        <h2>Documento</h2>
        <div class="stock-grid">
          <label class="stock-field">
            <span>Local de origem *</span>
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
            <span>Data da saída *</span>
            <InputText v-model="form.effective_date" type="date" :disabled="!editable" fluid />
          </label>
          <label class="stock-field">
            <span>Tipo *</span>
            <Select
              v-model="form.exit_type"
              :options="exitTypeOptions"
              option-label="label"
              option-value="value"
              :disabled="!editable"
              fluid
            />
          </label>
          <div class="stock-field">
            <span>Conferir por etiqueta</span>
            <div class="stock-switch">
              <InputSwitch v-model="form.require_label_scan" :disabled="!editable" />
              <small>{{ form.require_label_scan ? "Exige leitura" : "Confirmação manual" }}</small>
            </div>
          </div>
          <label class="stock-field stock-field--full">
            <span>Motivo *</span>
            <Textarea
              v-model="form.reason"
              rows="2"
              placeholder="Ex.: consumo da produção do dia, perda por queda, descarte por vencimento..."
              :disabled="!editable"
              fluid
            />
          </label>
        </div>
      </section>

      <section class="stock-card">
        <div class="stock-card__head">
          <div>
            <h2>Insumos retirados</h2>
            <p>Informe a quantidade na unidade do insumo. A separação escolhe os lotes.</p>
          </div>
          <Button v-if="editable" label="Adicionar insumo" icon="pi pi-plus" outlined size="small" @click="addRow" />
        </div>

        <div v-if="!rows.length" class="stock-empty">
          <i class="pi pi-inbox" />
          <p>Nenhum insumo na saída ainda.</p>
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
              />
            </label>
            <label class="stock-field">
              <span>Quantidade * <small v-if="unitOf(row)">({{ unitOf(row) }})</small></span>
              <InputNumber
                v-model="row.requested_quantity"
                :min-fraction-digits="0"
                :max-fraction-digits="3"
                :disabled="!editable"
                fluid
              />
            </label>
            <label class="stock-field">
              <span>Observação</span>
              <InputText v-model="row.notes" :disabled="!editable" fluid />
            </label>
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

      <section v-if="allocations.length" class="stock-card">
        <div class="stock-card__head">
          <div>
            <h2>Lotes separados</h2>
            <p>Retire fisicamente exatamente estes lotes — a ordem segue {{ strategyLabel }}.</p>
          </div>
        </div>
        <DataTable :value="allocations" size="small" class="stock-table">
          <Column field="ingredient_name" header="Insumo" />
          <Column field="lot_code" header="Lote" />
          <Column field="suggested_quantity" header="Quantidade" />
          <Column header="Entrada"><template #body="{ data }">{{ formatDate(data.lot_entered_at) }}</template></Column>
          <Column header="Validade"><template #body="{ data }">{{ formatDate(data.lot_expires_at) || "—" }}</template></Column>
          <Column header="Conferido">
            <template #body="{ data }">
              <Tag
                :value="data.is_confirmed ? 'Conferido' : 'Pendente'"
                :severity="data.is_confirmed ? 'success' : 'warning'"
                rounded
              />
            </template>
          </Column>
        </DataTable>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import InputNumber from "primevue/inputnumber";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import Select from "primevue/dropdown";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";
import Textarea from "primevue/textarea";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import { STOCK_EXIT_TYPE_OPTIONS, STOCK_PICKING_LABELS } from "../config/enums";
import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";

const props = defineProps({ id: { type: String, default: "" } });

const route = useRoute();
const router = useRouter();
const toast = useToast();
const confirm = useConfirm();

const loading = ref(true);
const saving = ref(false);
const suggesting = ref(false);
const posting = ref(false);
const error = ref("");
const locations = ref([]);
const ingredients = ref([]);
const allocations = ref([]);
const shortages = ref([]);
const exitTypeOptions = STOCK_EXIT_TYPE_OPTIONS;

const exitId = computed(() => props.id || route.params.id || "");
const isNew = computed(() => !exitId.value);

const form = reactive({
  location: null,
  effective_date: new Date().toISOString().slice(0, 10),
  exit_type: "consumption",
  reason: "",
  require_label_scan: false,
  picking_strategy: "fefo",
  status: "draft",
});

const rows = ref([]);
let rowSeq = 0;

const editable = computed(() => form.status === "draft");
const hasAllocations = computed(() => allocations.value.length > 0);
const strategyLabel = computed(() => STOCK_PICKING_LABELS[form.picking_strategy] || "FEFO");
const statusLabel = computed(
  () => ({ draft: "Rascunho", posted: "Confirmada", cancelled: "Cancelada" })[form.status] || form.status,
);
const statusSeverity = computed(
  () => ({ draft: "warning", posted: "success", cancelled: "danger" })[form.status] || "info",
);

function addRow() {
  rows.value.push({ _key: ++rowSeq, ingredient: null, requested_quantity: null, notes: "" });
}

function unitOf(row) {
  return ingredients.value.find((item) => item.id === row.ingredient)?.unit || "";
}

function formatDate(value) {
  if (!value) return "";
  const [year, month, day] = String(value).split("-");
  return day ? `${day}/${month}/${year}` : value;
}

function goBack() {
  router.push({ name: "estoque-saidas" });
}

function goToPicking() {
  router.push({ name: "estoque-saida-conferencia", params: { id: exitId.value } });
}

function toPayload() {
  return {
    location: form.location,
    effective_date: form.effective_date,
    exit_type: form.exit_type,
    reason: form.reason,
    require_label_scan: form.require_label_scan,
    items: rows.value.map((row) => ({
      ingredient: row.ingredient,
      requested_quantity: row.requested_quantity || 0,
      notes: row.notes || "",
    })),
  };
}

function applyExit(data) {
  Object.assign(form, {
    location: data.location,
    effective_date: data.effective_date,
    exit_type: data.exit_type,
    reason: data.reason || "",
    require_label_scan: !!data.require_label_scan,
    picking_strategy: data.picking_strategy || "fefo",
    status: data.status,
  });
  rows.value = (data.items || []).map((item) => ({
    _key: ++rowSeq,
    ingredient: item.ingredient,
    requested_quantity: Number(item.requested_quantity),
    notes: item.notes || "",
  }));
  allocations.value = (data.items || []).flatMap((item) => item.allocations || []);
}

async function persist() {
  const payload = toPayload();
  const { data } = exitId.value
    ? await api.patch(`/stock/exits/${exitId.value}/`, payload)
    : await api.post("/stock/exits/", payload);
  return data;
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const data = await persist();
    applyExit(data);
    toast.add({ severity: "success", summary: "Rascunho salvo", life: 2500 });
    if (!exitId.value) router.replace({ name: "estoque-saida-documento", params: { id: data.id } });
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    saving.value = false;
  }
}

async function suggest() {
  suggesting.value = true;
  error.value = "";
  try {
    const saved = await persist();
    const { data } = await api.post(`/stock/exits/${saved.id}/suggest_lots/`, {});
    applyExit(data.exit);
    shortages.value = data.shortages || [];
    if (!exitId.value) router.replace({ name: "estoque-saida-documento", params: { id: saved.id } });
    toast.add({
      severity: shortages.value.length ? "warn" : "success",
      summary: shortages.value.length ? "Separação parcial" : "Lotes separados",
      life: 3500,
    });
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    suggesting.value = false;
  }
}

function confirmPost() {
  confirm.require({
    header: "Confirmar a saída?",
    message: "O saldo dos lotes será baixado e a saída não poderá mais ser editada.",
    icon: "pi pi-exclamation-triangle",
    acceptLabel: "Confirmar saída",
    rejectLabel: "Voltar",
    accept: post,
  });
}

async function post() {
  posting.value = true;
  error.value = "";
  try {
    const { data } = await api.post(`/stock/exits/${exitId.value}/post_exit/`, {});
    applyExit(data);
    toast.add({ severity: "success", summary: "Saída confirmada", life: 3500 });
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    posting.value = false;
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
    if (settingsResponse.data) {
      form.picking_strategy = settingsResponse.data.picking_strategy || "fefo";
      form.require_label_scan = !!settingsResponse.data.require_label_scan_on_manual_exit;
      if (!form.location && settingsResponse.data.default_location) {
        form.location = settingsResponse.data.default_location;
      }
    }

    if (exitId.value) {
      const { data } = await api.get(`/stock/exits/${exitId.value}/`);
      applyExit(data);
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

.stock-doc__alert--warn { border-color: var(--warning); background: var(--warning-subtle); color: var(--warning-text); }
.stock-switch { display: flex; align-items: center; gap: 9px; min-height: var(--control-h); }
.stock-switch small { color: var(--text-muted); font-weight: var(--weight-medium); }
</style>
