<template>
  <section class="variations">
    <div class="variations__head">
      <h3>Variações <small>{{ rows.length }}</small></h3>
      <Button
        v-if="!readonly"
        label="Adicionar variação"
        icon="pi pi-plus"
        size="small"
        severity="secondary"
        outlined
        @click="openCreate"
      />
    </div>
    <DataTable :value="rows" data-key="id" class="variations__table" :row-hover="false" responsive-layout="scroll">
      <Column field="name" header="Variação">
        <template #body="{ data }"><strong class="variations__name">{{ data.name }}</strong></template>
      </Column>
      <Column header="Imagem" :body-style="{ width: '76px' }" :style="{ width: '76px' }">
        <template #body="{ data }">
          <img v-if="data.logo_p" :src="data.logo_p" :alt="data.name" class="variations__image" />
          <span v-else class="variations__no-image">—</span>
        </template>
      </Column>
      <Column header="Ajuste" header-class="dt-col-right" :body-style="{ textAlign: 'right', width: '130px' }" :style="{ width: '130px' }">
        <template #body="{ data }">{{ formatDelta(data.price_delta) }}</template>
      </Column>
      <Column header="Status" :body-style="{ width: '130px' }" :style="{ width: '130px' }">
        <template #body="{ data }">
          <span class="variations__badges">
            <Tag :value="data.is_active ? 'Ativa' : 'Inativa'" :severity="data.is_active ? 'success' : 'danger'" rounded />
          </span>
        </template>
      </Column>
      <Column v-if="!readonly" header="" :body-style="{ textAlign: 'right', width: '90px' }" :style="{ width: '90px' }">
        <template #body="{ data }">
          <Button icon="pi pi-pencil" text rounded aria-label="Editar variação" @click="openEdit(data)" />
          <Button icon="pi pi-trash" text rounded severity="danger" aria-label="Remover variação" @click="confirmRemove(data)" />
        </template>
      </Column>
      <template #empty>
        <div class="variations__empty">
          {{ readonly ? "Nenhuma variação cadastrada." : "Nenhuma variação ainda. Clique em \"Adicionar variação\"." }}
        </div>
      </template>
    </DataTable>
    <ProductVariationDialog
      v-model:visible="dialogOpen"
      v-model:editing="editing"
      :saving="saving"
      :dirty="dirty"
      :form-error="formError"
      :field-errors="fieldErrors"
      :image-options="imageOptions"
      @dirty="dirty = true"
      @save="save"
    />
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import Button from "primevue/button";
import Tag from "primevue/tag";
import DataTable from "primevue/datatable";
import Column from "primevue/column";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import ProductVariationDialog from "./ProductVariationDialog.vue";
import { ResourceService } from "../../services/ResourceService";
import { normalizeApiError } from "../../utils/apiError";
import { formatMoney } from "../../utils/format";

const props = defineProps({
  productId: { type: String, required: true },
  initialVariations: { type: Array, default: () => [] },
  productImages: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
});

const service = new ResourceService({ endpoint: "/menu/variations/" });
const confirm = useConfirm();
const toast = useToast();

function toRow(variation) {
  return {
    id: variation.id ?? null,
    name: variation.name ?? "",
    price_delta: Number(variation.price_delta ?? 0),
    is_active: variation.is_active ?? true,
    logo_image: variation.logo_image ?? null,
    logo_p: variation.logo_p ?? "",
  };
}

const rows = ref(props.initialVariations.map(toRow));

const dialogOpen = ref(false);
const saving = ref(false);
const dirty = ref(false);
const formError = ref("");
const fieldErrors = ref({});
const editing = ref(emptyForm());

function emptyForm() {
  return { id: null, name: "", price_delta: 0, is_active: true, logo_image: null, logo_p: "" };
}

const imageOptions = computed(() => props.productImages.map((image, index) => ({
  label: image.original_name || `Foto ${index + 1}`,
  value: image.id,
  url: image.url,
})));

function resetForm(data) {
  editing.value = data ? { ...data } : emptyForm();
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

function buildPayload() {
  return {
    product: props.productId,
    name: editing.value.name,
    price_delta: Number(editing.value.price_delta) || 0,
    is_active: !!editing.value.is_active,
    logo_image: editing.value.logo_image || null,
  };
}

async function save() {
  if (!editing.value.name.trim()) {
    fieldErrors.value = { name: "Informe um nome." };
    return;
  }
  saving.value = true;
  formError.value = "";
  fieldErrors.value = {};
  try {
    const payload = buildPayload();
    // restaurante/filial são herdados do produto no backend.
    const saved = editing.value.id ? await service.update(editing.value.id, payload) : await service.create(payload);
    upsertRow(toRow(saved));
    dialogOpen.value = false;
    toast.add({ severity: "success", summary: editing.value.id ? "Variação atualizada" : "Variação adicionada", life: 2000 });
  } catch (err) {
    const normalized = normalizeApiError(err);
    fieldErrors.value = normalized.fieldErrors;
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
    header: "Remover variação?",
    message: `Remover "${row.name}"? Esta ação não pode ser desfeita.`,
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
    toast.add({ severity: "success", summary: "Variação removida", life: 2000 });
  } catch (err) {
    toast.add({ severity: "error", summary: "Não foi possível remover", detail: normalizeApiError(err).message, life: 4000 });
  }
}

const formatDelta = (value) => {
  const n = Number(value) || 0;
  return `${n > 0 ? "+" : ""}${formatMoney(n)}`;
};
</script>

<style scoped src="./ProductVariationsEditor.css"></style>
