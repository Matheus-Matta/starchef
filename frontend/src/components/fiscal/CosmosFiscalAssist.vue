<template>
  <aside v-if="status.ready" class="cosmos-assist" :data-tone="tone" aria-live="polite">
    <span class="cosmos-assist__icon"><i class="pi pi-search" /></span>
    <div class="cosmos-assist__copy">
      <strong>Preenchimento pela Cosmos</strong>
      <span v-if="searching">Buscando produtos semelhantes a “{{ normalizedName }}”...</span>
      <span v-else-if="result">
        Encontrado: <b>{{ result.matched_product || normalizedName }}</b>.
        <template v-if="result.ncm"> NCM sugerido: <b>{{ result.ncm }}</b>.</template>
        <template v-if="result.cest"> CEST sugerido: <b>{{ result.cest }}</b>.</template>
      </span>
      <span v-else-if="message">{{ message }}</span>
      <span v-else>Digite pelo menos 3 caracteres no nome; a busca e o preenchimento acontecem automaticamente.</span>
      <small v-if="result?.warning">{{ result.warning }}</small>
    </div>
    <Button
      v-if="status.ready && normalizedName.length >= 3"
      type="button"
      icon="pi pi-refresh"
      text
      rounded
      :loading="searching"
      aria-label="Buscar novamente na Cosmos"
      @click="lookup(true)"
    />
  </aside>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import Button from "primevue/button";

import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";

const props = defineProps({
  name: { type: String, default: "" },
});
const emit = defineEmits(["suggestion"]);

const status = reactive({ active: false, configured: false, ready: false });
const searching = ref(false);
const result = ref(null);
const message = ref("");
const lastQuery = ref("");
let timer = null;
let requestSequence = 0;

const normalizedName = computed(() => String(props.name || "").trim().replace(/\s+/g, " "));
const tone = computed(() => {
  if (searching.value) return "info";
  if (message.value) return "warning";
  if (result.value) return "success";
  return "neutral";
});

function scheduleLookup() {
  clearTimeout(timer);
  result.value = null;
  message.value = "";
  if (!status.ready || normalizedName.value.length < 3) return;
  timer = setTimeout(() => lookup(false), 700);
}

async function loadStatus() {
  try {
    const { data } = await api.get("/fiscal/profiles/cosmos-status/", { skipRestaurantScope: true });
    Object.assign(status, data);
  } catch (error) {
    message.value = normalizeApiError(error).message;
  } finally {
    scheduleLookup();
  }
}

async function lookup(force) {
  const query = normalizedName.value;
  if (!status.ready || query.length < 3 || searching.value) return;
  if (!force && query === lastQuery.value) return;
  const sequence = ++requestSequence;
  searching.value = true;
  message.value = "";
  try {
    const { data } = await api.get("/fiscal/profiles/cosmos-suggest/", {
      params: { query },
      skipRestaurantScope: true,
    });
    if (sequence !== requestSequence) return;
    lastQuery.value = query;
    result.value = data;
    if (Object.keys(data.fields || {}).length) {
      emit("suggestion", data);
    } else {
      message.value = "A Cosmos encontrou um produto, mas não devolveu NCM ou CEST para preencher.";
    }
  } catch (error) {
    if (sequence !== requestSequence) return;
    result.value = null;
    message.value = normalizeApiError(error).message;
  } finally {
    if (sequence === requestSequence) searching.value = false;
  }
}

watch(normalizedName, () => {
  requestSequence += 1;
  searching.value = false;
  scheduleLookup();
});

onMounted(loadStatus);
onBeforeUnmount(() => clearTimeout(timer));
</script>

<style scoped>
.cosmos-assist { margin: 16px var(--card-pad) 0; display: grid; grid-template-columns: 38px 1fr auto; align-items: center; gap: 12px; padding: 13px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-sunken); }
.cosmos-assist[data-tone="success"] { border-color: color-mix(in srgb, var(--success-text) 28%, var(--border)); background: var(--success-subtle); }
.cosmos-assist[data-tone="warning"] { border-color: color-mix(in srgb, var(--warning-text) 25%, var(--border)); background: var(--warning-subtle); }
.cosmos-assist__icon { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 11px; background: var(--surface-card); color: var(--text-brand); }
.cosmos-assist__copy { min-width: 0; display: flex; flex-direction: column; gap: 4px; color: var(--text-muted); font-size: 12px; line-height: 1.4; }
.cosmos-assist__copy strong, .cosmos-assist__copy b { color: var(--text-strong); }
.cosmos-assist__copy a { color: var(--text-brand); font-weight: var(--weight-bold); }
.cosmos-assist__copy small { color: var(--warning-text); line-height: 1.35; }
@media (max-width: 620px) {
  .cosmos-assist { grid-template-columns: 34px 1fr; }
  .cosmos-assist > :deep(.p-button) { grid-column: 2; justify-self: start; }
}
</style>
