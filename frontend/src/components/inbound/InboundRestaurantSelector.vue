<template>
  <label class="inbound-unit">
    <span>Unidade para consultar a SEFAZ</span>
    <select :value="modelValue" :disabled="loading" @change="selectRestaurant">
      <option value="">Todas as unidades (somente visualizar)</option>
      <option v-for="restaurant in restaurants" :key="restaurant.id" :value="restaurant.id">
        {{ restaurant.trade_name || restaurant.legal_name }}
      </option>
    </select>
    <small v-if="error">{{ error }}</small>
    <small v-else>Escolha aqui a unidade usada na sincronização manual.</small>
  </label>
</template>

<script setup>
import { onMounted, ref } from "vue";

import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";

const props = defineProps({ modelValue: { type: String, default: "" } });
const emit = defineEmits(["update:modelValue"]);
const restaurants = ref([]);
const loading = ref(false);
const error = ref("");

function selectRestaurant(event) {
  emit("update:modelValue", event.target.value);
}

async function loadRestaurants() {
  loading.value = true;
  try {
    const { data } = await api.get("/restaurants/", {
      params: { is_active: true, page_size: 200 },
      skipRestaurantScope: true,
    });
    restaurants.value = data.results || data || [];
    if (!props.modelValue && restaurants.value.length === 1) {
      emit("update:modelValue", restaurants.value[0].id);
    }
  } catch (err) {
    error.value = normalizeApiError(err).message;
  } finally {
    loading.value = false;
  }
}

onMounted(loadRestaurants);
</script>

<style scoped>
.inbound-unit { display: flex; min-width: min(100%, 320px); flex-direction: column; gap: 5px; }
.inbound-unit span { color: var(--text-muted); font: var(--weight-bold) 10px/1 var(--font-sans); letter-spacing: var(--tracking-caps); text-transform: uppercase; }
.inbound-unit select { height: var(--control-h); padding: 0 34px 0 11px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-body); }
.inbound-unit small { color: var(--text-muted); font-size: 11px; }
@media (max-width: 720px) { .inbound-unit { width: 100%; } }
</style>
