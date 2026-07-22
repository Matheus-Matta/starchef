<template>
  <section class="paddons">
    <div class="paddons__head">
      <h3>Adicionais <small>{{ rows.length }}</small></h3>
    </div>

    <!-- Seletor + botão de adicionar (só na edição) -->
    <div v-if="!readonly" class="paddons__add">
      <Dropdown
        v-model="selected"
        :options="availableOptions"
        option-label="label"
        option-value="value"
        :loading="loadingOptions"
        placeholder="Selecionar adicional..."
        filter
        class="paddons__select"
      />
      <Button label="Adicionar" icon="pi pi-plus" :disabled="!selected || saving" :loading="saving" @click="add" />
    </div>

    <DataTable :value="rows" data-key="id" class="paddons__table" :row-hover="false" responsive-layout="scroll">
      <Column field="name" header="Adicional" />
      <Column header="Preço" header-class="dt-col-right" :body-style="{ textAlign: 'right', width: '120px' }" :style="{ width: '120px' }">
        <template #body="{ data }">{{ money(data.price) }}</template>
      </Column>
      <Column v-if="!readonly" header="" :body-style="{ textAlign: 'right', width: '56px' }" :style="{ width: '56px' }">
        <template #body="{ data }">
          <Button icon="pi pi-times" text rounded severity="danger" aria-label="Remover adicional" @click="remove(data)" />
        </template>
      </Column>
      <template #empty>
        <div class="paddons__empty">Nenhum adicional vinculado.</div>
      </template>
    </DataTable>
  </section>
</template>

<script setup>
/**
 * Vincula/desvincula adicionais a um produto na edição do produto.
 * Seletor de adicional + botão "Adicionar"; abaixo, a lista dos vinculados.
 * O vínculo é a M2M ProductAddon.products, operada por endpoints do produto.
 */
import { computed, onMounted, ref } from "vue";
import Dropdown from "primevue/dropdown";
import Button from "primevue/button";
import DataTable from "primevue/datatable";
import Column from "primevue/column";
import { useToast } from "primevue/usetoast";

import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";
import { formatMoney } from "../../utils/format";

const props = defineProps({
  productId: { type: String, required: true },
  initialAddons: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
});

const toast = useToast();
const money = formatMoney;

const rows = ref(props.initialAddons.map((addon) => ({ id: addon.id, name: addon.name, price: Number(addon.price ?? 0) })));
const selected = ref(null);
const saving = ref(false);

const allOptions = ref([]);
const loadingOptions = ref(false);
// Não oferece adicionais que já estão vinculados.
const availableOptions = computed(() => {
  const linked = new Set(rows.value.map((row) => row.id));
  return allOptions.value.filter((option) => !linked.has(option.value));
});

async function loadOptions() {
  loadingOptions.value = true;
  try {
    const res = await api.get("/menu/addons/", { params: { page_size: 200, ordering: "name" } });
    const list = res.data.results || res.data || [];
    allOptions.value = list.map((addon) => ({ label: addon.name, value: addon.id, name: addon.name, price: addon.price }));
  } catch {
    allOptions.value = [];
  } finally {
    loadingOptions.value = false;
  }
}

async function add() {
  if (!selected.value) return;
  saving.value = true;
  try {
    const { data } = await api.post(`/menu/products/${props.productId}/link-addon/`, { addon: selected.value });
    rows.value.push({ id: data.id, name: data.name, price: Number(data.price ?? 0) });
    selected.value = null;
    toast.add({ severity: "success", summary: "Adicional vinculado", life: 2000 });
  } catch (err) {
    toast.add({ severity: "error", summary: "Não foi possível vincular", detail: normalizeApiError(err).message, life: 4000 });
  } finally {
    saving.value = false;
  }
}

async function remove(row) {
  try {
    await api.post(`/menu/products/${props.productId}/unlink-addon/`, { addon: row.id });
    rows.value = rows.value.filter((r) => r.id !== row.id);
    toast.add({ severity: "success", summary: "Adicional desvinculado", life: 2000 });
  } catch (err) {
    toast.add({ severity: "error", summary: "Não foi possível desvincular", detail: normalizeApiError(err).message, life: 4000 });
  }
}

onMounted(loadOptions);
</script>

<style scoped>
.paddons { display: flex; flex-direction: column; gap: 12px; padding: 18px; border: 1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-sm); }
.paddons__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.paddons__head h3 { display: flex; align-items: center; gap: 8px; color: var(--text-strong); font: var(--weight-extra) 14px/1.2 var(--font-sans); }
.paddons__head small { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }

.paddons__add { display: flex; align-items: center; gap: 8px; }
.paddons__select { flex: 1; min-width: 0; }

.paddons__empty { color: var(--text-muted); font: var(--weight-medium) 13px/1.5 var(--font-sans); text-align: center; padding: 8px 0; }

.paddons__table :deep(.p-datatable-thead > tr > th) {
  padding: 7px 10px;
  background: var(--surface-sunken);
  color: var(--text-subtle);
  border-color: var(--border-subtle);
  font: var(--weight-bold) 10.5px/1 var(--font-table);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}
.paddons__table :deep(.p-datatable-tbody > tr) {
  background: var(--surface-sunken); /* contraste com o fundo do card */
}
.paddons__table :deep(.p-datatable-tbody > tr > td) {
  padding: 7px 10px;
  border-color: var(--border);
  font: var(--weight-medium) 13.5px/1.3 var(--font-table);
  color: var(--text-body);
  background: transparent;
}
.paddons__table :deep(.p-datatable-thead > tr > th.dt-col-right .p-column-header-content) {
  justify-content: flex-end;
}
.paddons__table :deep(.p-datatable-emptymessage > td) { border: none; background: transparent; }
</style>
