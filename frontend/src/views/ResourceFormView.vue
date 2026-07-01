<template>
  <div class="rform">

    <!-- Breadcrumb nav -->
    <nav class="rform__nav">
      <button class="rform__back" type="button" @click="goBack">
        <i class="pi pi-arrow-left" />
        <span>{{ title }}</span>
      </button>
      <i class="pi pi-chevron-right rform__sep" />
      <span class="rform__crumb">{{ isEdit ? "Editar" : "Novo" }}</span>
    </nav>

    <!-- Skeleton while loading record for edit -->
    <div v-if="fetching" class="rform__card">
      <div class="rform__card-header">
        <Skeleton width="240px" height="24px" />
        <Skeleton width="380px" height="16px" />
      </div>
      <div class="rform__body">
        <div v-for="i in formFields.length" :key="i" class="rform__field">
          <Skeleton width="110px" height="13px" />
          <Skeleton height="42px" border-radius="8px" />
        </div>
      </div>
    </div>

    <!-- Fetch error -->
    <div v-else-if="fetchError" class="rform__alert rform__alert--error">
      <i class="pi pi-exclamation-triangle" /> {{ fetchError }}
    </div>

    <!-- Form card -->
    <form v-else class="rform__card" novalidate @submit.prevent="submit">

      <div class="rform__card-header">
        <div class="rform__card-title">
          <h2>{{ isEdit ? `Editar — ${title}` : `Novo — ${title}` }}</h2>
          <p>{{ isEdit ? "Altere os campos e salve para confirmar." : "Preencha os campos para criar um novo registro." }}</p>
        </div>
      </div>

      <div class="rform__body">
        <div
          v-for="field in formFields"
          :key="field.name"
          class="rform__field"
          :class="{
            'rform__field--full': field.full || field.type === 'textarea' || field.type === 'boolean',
            'rform__field--error': !!fieldErrors[field.name],
          }"
        >
          <label :for="`f-${field.name}`" class="rform__label">
            {{ field.label }}
            <span v-if="field.required" class="rform__required" aria-hidden="true">*</span>
          </label>

          <!-- Toggle switch -->
          <div v-if="field.type === 'boolean'" class="rform__switch-row">
            <InputSwitch :id="`f-${field.name}`" v-model="formData[field.name]" />
            <span class="rform__switch-label">{{ formData[field.name] ? "Ativo" : "Inativo" }}</span>
          </div>

          <!-- Static dropdown -->
          <Dropdown
            v-else-if="field.type === 'dropdown'"
            :id="`f-${field.name}`"
            v-model="formData[field.name]"
            :options="field.options"
            option-label="label"
            option-value="value"
            :placeholder="field.placeholder || `Selecionar ${field.label.toLowerCase()}`"
            :class="['rform__select', { 'p-invalid': !!fieldErrors[field.name] }]"
            :show-clear="!field.required"
            filter
            fluid
          />

          <!-- Remote dropdown (options fetched from API) -->
          <Dropdown
            v-else-if="field.type === 'remote-dropdown'"
            :id="`f-${field.name}`"
            v-model="formData[field.name]"
            :options="remoteOptions[field.name] || []"
            option-label="label"
            option-value="value"
            :placeholder="field.placeholder || `Selecionar ${field.label.toLowerCase()}`"
            :class="['rform__select', { 'p-invalid': !!fieldErrors[field.name] }]"
            :show-clear="!field.required"
            :loading="!remoteOptions[field.name]"
            filter
            fluid
          />

          <!-- Textarea -->
          <Textarea
            v-else-if="field.type === 'textarea'"
            :id="`f-${field.name}`"
            v-model="formData[field.name]"
            :placeholder="field.placeholder || field.label"
            :rows="field.rows || 4"
            auto-resize
            :class="['rform__input', { 'p-invalid': !!fieldErrors[field.name] }]"
          />

          <!-- Password -->
          <Password
            v-else-if="field.type === 'password'"
            :id="`f-${field.name}`"
            v-model="formData[field.name]"
            :placeholder="field.placeholder || field.label"
            :feedback="false"
            toggle-mask
            :class="['rform__password', { 'p-invalid': !!fieldErrors[field.name] }]"
            :input-class="['rform__input', { 'p-invalid': !!fieldErrors[field.name] }]"
          />

          <!-- Number / decimal -->
          <InputText
            v-else-if="field.type === 'number' || field.type === 'decimal'"
            :id="`f-${field.name}`"
            v-model="formData[field.name]"
            type="number"
            :step="field.type === 'decimal' ? '0.01' : '1'"
            :min="field.min ?? '0'"
            :placeholder="field.placeholder || '0'"
            :class="['rform__input', { 'p-invalid': !!fieldErrors[field.name] }]"
          />

          <!-- Text / email / url (default) -->
          <InputText
            v-else
            :id="`f-${field.name}`"
            v-model="formData[field.name]"
            :type="field.inputType || 'text'"
            :placeholder="field.placeholder || field.label"
            :class="['rform__input', { 'p-invalid': !!fieldErrors[field.name] }]"
          />

          <!-- Per-field error -->
          <small v-if="fieldErrors[field.name]" class="rform__field-err">
            <i class="pi pi-exclamation-circle" />
            {{ fieldErrors[field.name] }}
          </small>
        </div>
      </div>

      <!-- Save error banner -->
      <div v-if="saveError" class="rform__alert rform__alert--error rform__alert--inline">
        <i class="pi pi-exclamation-triangle" /> {{ saveError }}
      </div>

      <div class="rform__footer">
        <Button type="button" label="Cancelar" severity="secondary" outlined @click="goBack" />
        <Button type="submit" :label="isEdit ? 'Salvar alteracoes' : 'Criar registro'" :loading="saving" icon="pi pi-check" />
      </div>
    </form>

  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, toRaw, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Dropdown from "primevue/dropdown";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import Skeleton from "primevue/skeleton";
import Textarea from "primevue/textarea";

import { api } from "../services/api";

const remoteOptions = reactive({});

const props = defineProps({
  endpoint: { type: String, required: true },
  title: { type: String, required: true },
  formFields: { type: Array, required: true },
  id: { type: String, default: null },
  globalScope: { type: Boolean, default: false },
});

const route = useRoute();
const router = useRouter();

const isEdit = computed(() => !!(props.id || route.params.id));
const recordId = computed(() => props.id || route.params.id);

const fetching = ref(false);
const fetchError = ref("");
const saving = ref(false);
const saveError = ref("");
const fieldErrors = ref({});

function buildInitialData() {
  const d = {};
  for (const f of props.formFields) {
    if (f.default !== undefined) {
      d[f.name] = f.default;
    } else if (f.type === "boolean") {
      d[f.name] = true;
    } else {
      d[f.name] = "";
    }
  }
  return d;
}

const formData = reactive(buildInitialData());

async function fetchRecord() {
  if (!isEdit.value) return;
  fetching.value = true;
  fetchError.value = "";
  try {
    const res = await api.get(`${props.endpoint}${recordId.value}/`, { skipRestaurantScope: props.globalScope });
    for (const f of props.formFields) {
      if (res.data[f.name] !== undefined) {
        formData[f.name] = res.data[f.name];
      }
    }
  } catch {
    fetchError.value = "Nao foi possivel carregar o registro.";
  } finally {
    fetching.value = false;
  }
}

function buildPayload() {
  const raw = toRaw(formData);
  const payload = {};
  for (const f of props.formFields) {
    let val = raw[f.name];
    if (f.type === "number" && val !== "" && val !== null && val !== undefined) {
      val = parseInt(val, 10);
    } else if (f.type === "decimal" && val !== "" && val !== null && val !== undefined) {
      val = parseFloat(val);
    }
    payload[f.name] = val;
  }
  return payload;
}

async function submit() {
  saving.value = true;
  saveError.value = "";
  fieldErrors.value = {};
  try {
    const payload = buildPayload();
    if (isEdit.value) {
      await api.patch(`${props.endpoint}${recordId.value}/`, payload);
    } else {
      await api.post(props.endpoint, payload);
    }
    goBack();
  } catch (err) {
    const body = err?.response?.data;
    // Support both wrapped format {error:{message:{...}}} and flat DRF format {field:[...]}
    const detail = body?.error?.message ?? body;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const errs = {};
      let hasFieldError = false;
      for (const [key, val] of Object.entries(detail)) {
        const msg = Array.isArray(val) ? val.join(" ") : String(val);
        if (key === "detail" || key === "non_field_errors") {
          saveError.value = msg;
        } else {
          errs[key] = msg;
          hasFieldError = true;
        }
      }
      fieldErrors.value = errs;
      if (!saveError.value && hasFieldError) {
        saveError.value = "Corrija os campos destacados e tente novamente.";
      }
    } else {
      saveError.value = "Erro ao salvar. Tente novamente.";
    }
  } finally {
    saving.value = false;
  }
}

function goBack() {
  router.push({ name: String(route.name).replace(/--(?:novo|editar)$/, "") });
}

async function loadRemoteOptions() {
  for (const field of props.formFields) {
    if (field.type !== "remote-dropdown" || !field.endpoint) continue;
    try {
      const res = await api.get(field.endpoint, { params: { page_size: 200 } });
      const rows = res.data.results || res.data || [];
      remoteOptions[field.name] = rows.map((row) => ({
        label: String(row[field.optionLabel ?? "name"] ?? row.id),
        value: row[field.optionValue ?? "id"],
      }));
    } catch {
      remoteOptions[field.name] = [];
    }
  }
}

onMounted(async () => {
  await Promise.all([fetchRecord(), loadRemoteOptions()]);
});
watch(() => recordId.value, fetchRecord);
</script>

<style scoped>
/* ── Layout shell ──────────────────────────────────────────── */
.rform {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
}

/* ── Breadcrumb nav ────────────────────────────────────────── */
.rform__nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rform__back {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  color: var(--text-muted);
  font: var(--weight-semibold) 13px/1 var(--font-sans);
  cursor: pointer;
  transition: background var(--dur-base), color var(--dur-base), border-color var(--dur-base);
}

.rform__back:hover {
  background: var(--surface-hover);
  border-color: var(--border-strong, var(--border));
  color: var(--text-body);
}

.rform__back .pi-arrow-left {
  font-size: 11px;
}

.rform__sep {
  font-size: 10px;
  color: var(--text-subtle);
}

.rform__crumb {
  color: var(--text-strong);
  font: var(--weight-bold) 13px/1 var(--font-sans);
}

/* ── Card ──────────────────────────────────────────────────── */
.rform__card {
  width: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.rform__card-header {
  padding: 22px 28px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.rform__card-title h2 {
  color: var(--text-strong);
  font: var(--weight-extra) 20px/1.2 var(--font-sans);
}

.rform__card-title p {
  margin-top: 5px;
  color: var(--text-muted);
  font: var(--weight-medium) 13px/1.5 var(--font-sans);
}

/* ── Fields grid ───────────────────────────────────────────── */
.rform__body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 22px 28px;
  padding: 28px;
}

.rform__field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rform__field--full {
  grid-column: 1 / -1;
}

.rform__field--error .rform__label {
  color: #dc2626;
}

.rform__field--error .rform__input,
.rform__field--error :deep(.p-inputtext),
.rform__field--error :deep(.p-dropdown),
.rform__field--error :deep(.p-textarea) {
  border-color: #ef4444 !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, #ef4444 12%, transparent) !important;
}

/* ── Label ─────────────────────────────────────────────────── */
.rform__label {
  color: var(--text-strong);
  font: var(--weight-bold) 12.5px/1.2 var(--font-sans);
  letter-spacing: 0.01em;
}

.rform__required {
  color: #ef4444;
  margin-left: 3px;
}

/* ── Inputs ────────────────────────────────────────────────── */
.rform__input {
  width: 100%;
  height: 42px;
  padding: 0 13px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
  color: var(--text-strong);
  font: var(--weight-medium) 14px/1 var(--font-sans);
  transition: border-color 120ms, box-shadow 120ms;
}

.rform__input:focus {
  outline: none;
  border-color: var(--ring);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ring) 15%, transparent);
}

.rform__input.p-invalid {
  border-color: #ef4444;
}

.rform__input.p-invalid:focus {
  box-shadow: 0 0 0 3px color-mix(in srgb, #ef4444 15%, transparent);
}

/* Textarea: override height */
.rform__input:is(textarea) {
  height: auto;
  padding: 11px 13px;
  resize: vertical;
  line-height: 1.55;
}

/* ── Select / Dropdown ─────────────────────────────────────── */
.rform__select {
  width: 100%;
}

/* ── Switch row ─────────────────────────────────────────────── */
.rform__switch-row {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 42px;
}

.rform__switch-label {
  color: var(--text-body);
  font: var(--weight-semibold) 13.5px/1 var(--font-sans);
}

/* ── Password ───────────────────────────────────────────────── */
.rform__password {
  width: 100%;
}

/* ── Field error ────────────────────────────────────────────── */
.rform__field-err {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #ef4444;
  font: var(--weight-medium) 12px/1.3 var(--font-sans);
}

.rform__field-err .pi {
  font-size: 12px;
}

/* ── Alert banners ──────────────────────────────────────────── */
.rform__alert {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 16px;
  border-radius: var(--radius-md);
  font: var(--weight-semibold) 13px/1.4 var(--font-sans);
}

.rform__alert--error {
  background: color-mix(in srgb, #ef4444 9%, var(--surface-card));
  border: 1px solid color-mix(in srgb, #ef4444 24%, transparent);
  color: #dc2626;
}

.rform__alert--inline {
  margin: 0 28px;
  border-radius: var(--radius-md);
}

/* ── Footer ─────────────────────────────────────────────────── */
.rform__footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 18px 28px;
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-base);
}

/* ── PrimeVue structural overrides (dimensionamento apenas) ─── */

/* Inputs: garantir largura e altura corretas */
:deep(.p-inputtext) {
  width: 100%;
  height: 42px;
  padding: 0 13px;
  font: var(--weight-medium) 14px/1 var(--font-sans);
}

/* Dropdown: largura + altura; cores vêm do primevue-tokens.css global */
:deep(.p-dropdown) {
  width: 100%;
  height: 42px;
}

:deep(.p-dropdown-label),
:deep(.p-dropdown-label.p-inputtext) {
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 13px;
  font: var(--weight-medium) 14px/1 var(--font-sans);
}

:deep(.p-dropdown-panel) {
  z-index: 9999 !important;
}

/* Textarea */
:deep(.p-textarea) {
  width: 100%;
  padding: 11px 13px;
  font: var(--weight-medium) 14px/1.55 var(--font-sans);
  resize: vertical;
}

/* Password */
:deep(.p-password) {
  width: 100%;
}

:deep(.p-password input) {
  width: 100%;
  height: 42px;
}

/* Button */
:deep(.p-button) {
  height: 42px;
  font: var(--weight-bold) 13px/1 var(--font-sans);
  border-radius: var(--radius-md);
}

/* ── Responsive ─────────────────────────────────────────────── */
@media (max-width: 720px) {
  .rform__body {
    grid-template-columns: 1fr;
    padding: 20px;
    gap: 18px;
  }

  .rform__field--full {
    grid-column: 1;
  }

  .rform__card-header {
    padding: 18px 20px 16px;
  }

  .rform__footer {
    padding: 14px 20px;
  }

  .rform__alert--inline {
    margin: 0 20px;
  }
}
</style>
