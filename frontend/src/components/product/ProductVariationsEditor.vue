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

    <!-- Modal reutilizável de criação/edição (STC-024 / STC-025) -->
    <AppEntityDialog
      v-model:visible="dialogOpen"
      entity="variação"
      :mode="editing.id ? 'edit' : 'create'"
      :saving="saving"
      :dirty="dirty"
      width="480px"
      @save="save"
    >
      <AppErrorSummary :message="formError" />
      <AppFormGrid :columns="2">
        <AppFormField label="Nome" name="name" :error="fieldErrors.name" required full>
          <template #default="{ fieldId, invalid }">
            <InputText :id="fieldId" v-model="editing.name" :class="{ 'p-invalid': invalid }" placeholder="Ex.: Grande, Sem cebola" @update:model-value="dirty = true" />
          </template>
        </AppFormField>
        <AppFormField label="Ajuste de preço (R$)" name="price_delta" :error="fieldErrors.price_delta" help="Use valores negativos para desconto.">
          <template #default="{ fieldId, invalid }">
            <InputNumber :id="fieldId" v-model="editing.price_delta" :class="{ 'p-invalid': invalid }" mode="currency" currency="BRL" locale="pt-BR" :min-fraction-digits="2" @update:model-value="dirty = true" />
          </template>
        </AppFormField>
        <AppFormField label="Ativa">
          <div class="variations__switch">
            <InputSwitch v-model="editing.is_active" @update:model-value="dirty = true" />
            <span>{{ editing.is_active ? "Ativa" : "Inativa" }}</span>
          </div>
        </AppFormField>
      </AppFormGrid>
    </AppEntityDialog>
  </section>
</template>

<script setup>
/**
 * Gerencia (lista/cria/edita/remove) as variações de um produto na própria
 * página de edição, agora via modal reutilizável (Sprint 2 · STC-024/025/026).
 *
 * Uso: :key="productId" no componente pai para reiniciar o estado ao trocar
 * de produto (evita sincronizar props via watch).
 */
import { ref } from "vue";
import Button from "primevue/button";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import InputNumber from "primevue/inputnumber";
import Tag from "primevue/tag";
import DataTable from "primevue/datatable";
import Column from "primevue/column";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import AppEntityDialog from "../form/AppEntityDialog.vue";
import AppFormGrid from "../form/AppFormGrid.vue";
import AppFormField from "../form/AppFormField.vue";
import AppErrorSummary from "../form/AppErrorSummary.vue";
import { ResourceService } from "../../services/ResourceService";
import { normalizeApiError } from "../../utils/apiError";
import { formatMoney } from "../../utils/format";

const props = defineProps({
  productId: { type: String, required: true },
  initialVariations: { type: Array, default: () => [] },
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
  return { id: null, name: "", price_delta: 0, is_active: true };
}

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

<style scoped>
.variations {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-sunken); /* card mais escuro para contraste */
  box-shadow: var(--shadow-sm);
}

.variations__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.variations__head h3 { display: flex; align-items: center; gap: 8px; color: var(--text-strong); font: var(--weight-extra) 14px/1.2 var(--font-sans); }
.variations__head small { color: var(--text-muted); font: var(--weight-semibold) 12px/1 var(--font-sans); }
.variations__empty { color: var(--text-muted); font: var(--weight-medium) 13px/1.5 var(--font-sans); text-align: center; padding: 8px 0; }
.variations__switch { display: flex; align-items: center; gap: 10px; height: var(--control-h); color: var(--text-body); font: var(--weight-semibold) 13px/1 var(--font-sans); }

/* DataTable com linhas mais claras que o card (contraste) */
.variations__name { color: var(--text-strong); font: var(--weight-bold) 13.5px/1.2 var(--font-table); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.variations__badges { display: inline-flex; gap: 6px; flex-shrink: 0; }

.variations__table :deep(.p-datatable-thead > tr > th) {
  padding: 7px 10px;
  background: transparent;
  color: var(--text-subtle);
  border-color: var(--border);
  font: var(--weight-bold) 10.5px/1 var(--font-table);
  text-transform: uppercase;
  letter-spacing: var(--tracking-caps);
}
.variations__table :deep(.p-datatable-thead > tr > th.dt-col-right .p-column-header-content) {
  justify-content: flex-end;
}
/* Linhas como "cartões" separados: gap entre elas + cantos arredondados */
.variations__table :deep(.p-datatable-table) { border-collapse: separate; border-spacing: 0 6px; }
.variations__table :deep(.p-datatable-tbody > tr > td) {
  padding: 9px 12px;
  border: none;
  background: var(--surface-card); /* célula mais clara que o card escuro */
  font: var(--weight-medium) 13.5px/1.3 var(--font-table);
  color: var(--text-body);
}
.variations__table :deep(.p-datatable-tbody > tr > td:first-child) { border-radius: var(--radius-md) 0 0 var(--radius-md); }
.variations__table :deep(.p-datatable-tbody > tr > td:last-child) { border-radius: 0 var(--radius-md) var(--radius-md) 0; }
.variations__table :deep(.p-datatable-emptymessage > td) { border: none; background: transparent; }
</style>
