<template>
  <AppEntityDialog
    :visible="visible"
    entity="perfil fiscal"
    :mode="profile ? 'edit' : 'create'"
    :saving="saving"
    :dirty="dirty"
    width="640px"
    @update:visible="$emit('update:visible', $event)"
    @save="save"
  >
    <AppErrorSummary :message="formError" />
    <AppFormGrid :columns="2">
      <AppFormField label="Nome" name="name" :error="fieldErrors.name" required full>
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" v-model="form.name" :class="{ 'p-invalid': invalid }" placeholder="Ex.: Prato padrão, Bebida" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="NCM" name="ncm" :error="fieldErrors.ncm">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" v-model="form.ncm" :class="{ 'p-invalid': invalid }" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="CEST" name="cest" :error="fieldErrors.cest">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" v-model="form.cest" :class="{ 'p-invalid': invalid }" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="CFOP de venda" name="cfop" :error="fieldErrors.cfop">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" v-model="form.cfop" :class="{ 'p-invalid': invalid }" placeholder="5102" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="Origem da mercadoria" name="origem" :error="fieldErrors.origem">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" v-model="form.origem" :class="{ 'p-invalid': invalid }" placeholder="0" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="CSOSN (Simples Nacional)" name="csosn" :error="fieldErrors.csosn">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" v-model="form.csosn" :class="{ 'p-invalid': invalid }" placeholder="102" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="CST ICMS (regime normal)" name="cst_icms" :error="fieldErrors.cst_icms">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" v-model="form.cst_icms" :class="{ 'p-invalid': invalid }" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="Alíquota ICMS (%)" name="icms_rate" :error="fieldErrors.icms_rate">
        <template #default="{ fieldId, invalid }">
          <InputNumber :id="fieldId" v-model="form.icms_rate" :class="{ 'p-invalid': invalid }" :min-fraction-digits="2" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="CST PIS" name="pis_cst" :error="fieldErrors.pis_cst">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" v-model="form.pis_cst" :class="{ 'p-invalid': invalid }" placeholder="49" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="Alíquota PIS (%)" name="pis_rate" :error="fieldErrors.pis_rate">
        <template #default="{ fieldId, invalid }">
          <InputNumber :id="fieldId" v-model="form.pis_rate" :class="{ 'p-invalid': invalid }" :min-fraction-digits="2" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="CST COFINS" name="cofins_cst" :error="fieldErrors.cofins_cst">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" v-model="form.cofins_cst" :class="{ 'p-invalid': invalid }" placeholder="49" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="Alíquota COFINS (%)" name="cofins_rate" :error="fieldErrors.cofins_rate">
        <template #default="{ fieldId, invalid }">
          <InputNumber :id="fieldId" v-model="form.cofins_rate" :class="{ 'p-invalid': invalid }" :min-fraction-digits="2" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="Tributos aprox. (Lei 12.741) (%)" name="approx_tax_rate" :error="fieldErrors.approx_tax_rate" full>
        <template #default="{ fieldId, invalid }">
          <InputNumber :id="fieldId" v-model="form.approx_tax_rate" :class="{ 'p-invalid': invalid }" :min-fraction-digits="2" @update:model-value="dirty = true" />
        </template>
      </AppFormField>
      <AppFormField label="Perfil padrão do restaurante">
        <div class="fpd__switch">
          <InputSwitch v-model="form.is_default" @update:model-value="dirty = true" />
          <span>{{ form.is_default ? "Sim" : "Não" }}</span>
        </div>
      </AppFormField>
      <AppFormField label="Ativo">
        <div class="fpd__switch">
          <InputSwitch v-model="form.is_active" @update:model-value="dirty = true" />
          <span>{{ form.is_active ? "Ativo" : "Inativo" }}</span>
        </div>
      </AppFormField>
    </AppFormGrid>
  </AppEntityDialog>
</template>

<script setup>
/**
 * Modal de criar/editar um perfil fiscal (FiscalProfile) — componente
 * genérico e reutilizável: usado na seção fiscal do restaurante e também no
 * formulário de produto (criação rápida sem sair da tela), bastando passar
 * `restaurantId`/`branchId`.
 */
import { reactive, ref, watch } from "vue";
import InputNumber from "primevue/inputnumber";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";

import AppEntityDialog from "../form/AppEntityDialog.vue";
import AppFormGrid from "../form/AppFormGrid.vue";
import AppFormField from "../form/AppFormField.vue";
import AppErrorSummary from "../form/AppErrorSummary.vue";
import { ResourceService } from "../../services/ResourceService";
import { normalizeApiError } from "../../utils/apiError";

const props = defineProps({
  visible: { type: Boolean, default: false },
  restaurantId: { type: String, required: true },
  branchId: { type: String, required: true },
  /** Perfil a editar; null/undefined cria um novo. */
  profile: { type: Object, default: null },
});

const emit = defineEmits(["update:visible", "saved"]);

const service = new ResourceService({ endpoint: "/fiscal/profiles/", globalScope: true });

const saving = ref(false);
const dirty = ref(false);
const formError = ref("");
const fieldErrors = ref({});

function emptyForm() {
  return {
    name: "", ncm: "", cest: "", cfop: "5102", origem: "0", csosn: "", cst_icms: "",
    icms_rate: 0, pis_cst: "49", pis_rate: 0, cofins_cst: "49", cofins_rate: 0,
    approx_tax_rate: 0, is_default: false, is_active: true,
  };
}

const form = reactive(emptyForm());

// Reabre com os dados certos toda vez que o modal abre (criar limpo, editar preenchido).
watch(
  () => props.visible,
  (open) => {
    if (!open) return;
    Object.assign(form, props.profile ? { ...emptyForm(), ...props.profile } : emptyForm());
    formError.value = "";
    fieldErrors.value = {};
    dirty.value = false;
  },
);

async function save() {
  if (!form.name.trim()) {
    fieldErrors.value = { name: "Informe um nome." };
    return;
  }
  saving.value = true;
  formError.value = "";
  fieldErrors.value = {};
  try {
    const payload = { ...form, restaurant: props.restaurantId, branch: props.branchId };
    const saved = props.profile?.id
      ? await service.update(props.profile.id, payload)
      : await service.create(payload);
    emit("saved", saved);
    emit("update:visible", false);
  } catch (err) {
    const normalized = normalizeApiError(err);
    fieldErrors.value = normalized.fieldErrors;
    formError.value = normalized.message;
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.fpd__switch { display: flex; align-items: center; gap: 10px; height: var(--control-h); color: var(--text-body); font: var(--weight-semibold) 13px/1 var(--font-sans); }
</style>
