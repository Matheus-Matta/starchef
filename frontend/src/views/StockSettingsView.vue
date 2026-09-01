<template>
  <div class="stock-doc">
    <header class="stock-doc__head">
      <div>
        <span class="stock-doc__eyebrow">ESTOQUE</span>
        <h1>Configuração do estoque</h1>
        <p>Estas regras valem para toda a conta: como os lotes são escolhidos, se a validade é obrigatória e o que o sistema bloqueia. O armazém é quem diz onde o estoque está.</p>
      </div>
      <Button label="Salvar configurações" icon="pi pi-save" :loading="saving" :disabled="loading" @click="save" />
    </header>

    <div v-if="error" class="stock-doc__alert"><i class="pi pi-exclamation-triangle" /> {{ error }}</div>

    <div v-if="isDefault && !loading" class="stock-doc__alert stock-doc__alert--info">
      <i class="pi pi-info-circle" />
      <span>Esta conta ainda não tem configuração de estoque. Os valores abaixo são os padrões recomendados e passam a valer para todos os restaurantes ao salvar.</span>
    </div>

    <div v-if="loading" class="stock-card"><Skeleton height="240px" /></div>

    <template v-else>
      <section class="stock-card">
        <div class="stock-card__head">
          <div>
            <h2>Separação de lotes</h2>
            <p>Qual lote o sistema indica primeiro quando alguém retira um insumo.</p>
          </div>
        </div>
        <div class="stock-grid">
          <label class="stock-field stock-field--wide">
            <span>Estratégia</span>
            <Select
              v-model="form.picking_strategy"
              :options="pickingOptions"
              option-label="label"
              option-value="value"
              fluid
            />
            <small>{{ strategyHint }}</small>
          </label>
          <label class="stock-field stock-field--wide">
            <span>Local padrão</span>
            <Select
              v-model="form.default_location"
              :options="locations"
              option-label="name"
              option-value="id"
              placeholder="Nenhum"
              show-clear
              fluid
            />
            <small>Sugerido nas entradas, saídas e nas baixas automáticas de venda.</small>
          </label>
        </div>
      </section>

      <section class="stock-card">
        <div class="stock-card__head">
          <div>
            <h2>Validade</h2>
            <p>Sem controle de validade, o FEFO não tem por onde ordenar — ele passa a se comportar como FIFO.</p>
          </div>
        </div>
        <div class="stock-grid">
          <div class="stock-field">
            <span>Exigir validade nas entradas</span>
            <div class="stock-switch">
              <InputSwitch v-model="form.expiry_control_enabled" />
              <small>{{ form.expiry_control_enabled ? "Obrigatória em toda linha" : "Opcional" }}</small>
            </div>
          </div>
          <label class="stock-field">
            <span>Avisar com antecedência (dias)</span>
            <InputNumber v-model="form.expiry_warning_days" :min="0" :max="365" show-buttons fluid />
          </label>
          <div class="stock-field">
            <span>Bloquear estoque vencido</span>
            <div class="stock-switch">
              <InputSwitch v-model="form.block_expired_stock" />
              <small>{{ form.block_expired_stock ? "Nunca sugerido" : "Pode ser sugerido" }}</small>
            </div>
          </div>
        </div>
      </section>

      <section class="stock-card">
        <div class="stock-card__head">
          <div>
            <h2>Conferência e saldo</h2>
            <p>O que o sistema exige antes de deixar uma retirada ser confirmada.</p>
          </div>
        </div>
        <div class="stock-grid">
          <div class="stock-field">
            <span>Exigir leitura de etiqueta na saída manual</span>
            <div class="stock-switch">
              <InputSwitch v-model="form.require_label_scan_on_manual_exit" />
              <small>{{ form.require_label_scan_on_manual_exit ? "Cada lote é conferido" : "Confirmação manual" }}</small>
            </div>
          </div>
          <div class="stock-field">
            <span>Permitir saldo negativo</span>
            <div class="stock-switch">
              <InputSwitch v-model="form.allow_negative_stock" />
              <small>{{ form.allow_negative_stock ? "Permitido" : "Bloqueado" }}</small>
            </div>
          </div>
          <label class="stock-field">
            <span>Modelo de etiqueta padrão</span>
            <Select
              v-model="form.default_label_template"
              :options="templates"
              option-label="name"
              option-value="id"
              placeholder="Nenhum"
              show-clear
              fluid
            />
          </label>
        </div>
        <div v-if="form.allow_negative_stock" class="stock-doc__alert stock-doc__alert--warn">
          <i class="pi pi-exclamation-triangle" />
          <span>
            Com saldo negativo permitido, uma retirada maior que o disponível passa mesmo assim.
            Use apenas enquanto o inventário inicial ainda não fechou.
          </span>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import InputSwitch from "primevue/inputswitch";
import Select from "primevue/dropdown";
import Skeleton from "primevue/skeleton";
import { useToast } from "primevue/usetoast";

import { STOCK_PICKING_OPTIONS } from "../config/enums";
import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";

const toast = useToast();
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const locations = ref([]);
const templates = ref([]);
const settingsId = ref(null);
const pickingOptions = STOCK_PICKING_OPTIONS;

const form = reactive({
  picking_strategy: "fefo",
  default_location: null,
  expiry_control_enabled: false,
  expiry_warning_days: 7,
  block_expired_stock: true,
  allow_negative_stock: false,
  require_label_scan_on_manual_exit: false,
  default_label_template: null,
});

/** Sem `id`, ninguém salvou nada ainda e a tela está mostrando os padrões. */
const isDefault = computed(() => !settingsId.value);

const strategyHint = computed(() =>
  form.picking_strategy === "fefo"
    ? "Sai primeiro o lote válido que vence antes — reduz descarte por vencimento."
    : "Sai primeiro o lote que entrou antes — indicado quando não há controle de validade.",
);

function applySettings(data) {
  settingsId.value = data.id || null;
  Object.assign(form, {
    picking_strategy: data.picking_strategy || "fefo",
    default_location: data.default_location || null,
    expiry_control_enabled: !!data.expiry_control_enabled,
    expiry_warning_days: Number(data.expiry_warning_days ?? 7),
    block_expired_stock: data.block_expired_stock !== false,
    allow_negative_stock: !!data.allow_negative_stock,
    require_label_scan_on_manual_exit: !!data.require_label_scan_on_manual_exit,
    default_label_template: data.default_label_template || null,
  });
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const payload = { ...form };
    const { data } = settingsId.value
      ? await api.patch(`/stock/settings/${settingsId.value}/`, payload)
      : await api.post("/stock/settings/", payload);
    applySettings(data);
    toast.add({ severity: "success", summary: "Configuração salva", life: 3000 });
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    saving.value = false;
  }
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [settingsResponse, locationsResponse, templatesResponse] = await Promise.all([
      api.get("/stock/settings/current/"),
      api.get("/stock/locations/", { params: { is_active: true, page_size: 200 } }),
      api.get("/stock/label-templates/", { params: { is_active: true, page_size: 100 } }),
    ]);
    applySettings(settingsResponse.data || {});
    locations.value = locationsResponse.data.results || locationsResponse.data;
    templates.value = templatesResponse.data.results || templatesResponse.data;
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
.stock-doc__alert--warn { margin-top: 14px; border-color: var(--warning); background: var(--warning-subtle); color: var(--warning-text); }
.stock-switch { display: flex; align-items: center; gap: 9px; min-height: var(--control-h); }
.stock-switch small { color: var(--text-muted); font-weight: var(--weight-medium); }
</style>
