<template>
  <AppFormSection title="Endereço" icon="map-pin" :description="description">
    <AppFormGrid :columns="4">
      <AppFormField label="CEP" name="cep" :error="errors.cep" :readonly="readonly" :required="required">
        <template #default="{ fieldId, invalid }">
          <span class="appaddr__cep">
            <InputText
              :id="fieldId"
              :model-value="model.cep"
              :class="{ 'p-invalid': invalid }"
              :disabled="readonly"
              inputmode="numeric"
              placeholder="00000-000"
              maxlength="9"
              @update:model-value="onCepInput"
              @blur="maybeLookup"
            />
            <Button
              v-if="!readonly && autoFill"
              type="button"
              icon="pi pi-search"
              text
              :loading="looking"
              aria-label="Buscar endereço pelo CEP"
              @click="lookup"
            />
          </span>
        </template>
      </AppFormField>

      <AppFormField class="appaddr--wide" label="Logradouro" name="street" :error="errors.street" :readonly="readonly" full>
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" :model-value="model.street" :class="{ 'p-invalid': invalid }" :disabled="readonly" placeholder="Rua, avenida..." @update:model-value="set('street', $event)" />
        </template>
      </AppFormField>

      <AppFormField label="Número" name="number" :error="errors.number" :readonly="readonly">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" :model-value="model.number" :class="{ 'p-invalid': invalid }" :disabled="readonly" placeholder="123" @update:model-value="set('number', $event)" />
        </template>
      </AppFormField>

      <AppFormField label="Complemento" name="complement" :error="errors.complement" :readonly="readonly">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" :model-value="model.complement" :class="{ 'p-invalid': invalid }" :disabled="readonly" placeholder="Apto, bloco..." @update:model-value="set('complement', $event)" />
        </template>
      </AppFormField>

      <AppFormField label="Bairro" name="district" :error="errors.district" :readonly="readonly">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" :model-value="model.district" :class="{ 'p-invalid': invalid }" :disabled="readonly" @update:model-value="set('district', $event)" />
        </template>
      </AppFormField>

      <AppFormField label="Cidade" name="city" :error="errors.city" :readonly="readonly">
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" :model-value="model.city" :class="{ 'p-invalid': invalid }" :disabled="readonly" @update:model-value="set('city', $event)" />
        </template>
      </AppFormField>

      <AppFormField label="UF" name="state" :error="errors.state" :readonly="readonly">
        <template #default="{ fieldId, invalid }">
          <Dropdown :id="fieldId" :model-value="model.state" :options="UFS" :class="{ 'p-invalid': invalid }" :disabled="readonly" placeholder="UF" show-clear filter fluid @update:model-value="set('state', $event)" />
        </template>
      </AppFormField>

      <AppFormField label="Ponto de referência" name="reference" :error="errors.reference" :readonly="readonly" full>
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" :model-value="model.reference" :class="{ 'p-invalid': invalid }" :disabled="readonly" placeholder="Próximo a..." @update:model-value="set('reference', $event)" />
        </template>
      </AppFormField>
    </AppFormGrid>

    <small v-if="lookupError" class="appaddr__hint">
      <AppIcon name="alert-circle" :size="12" /> {{ lookupError }}
    </small>
  </AppFormSection>
</template>

<script setup>
/**
 * Formulário de endereço brasileiro reutilizável (Sprint 0 · STC-005 / STC-041).
 * Máscara de CEP, seleção de UF e preenchimento automático por CEP (ViaCEP),
 * tolerante a falha do provedor — nunca bloqueia o cadastro.
 *
 * v-model: objeto de endereço com chaves
 *   { cep, street, number, complement, district, city, state, reference }
 */
import { computed, ref } from "vue";
import InputText from "primevue/inputtext";
import Dropdown from "primevue/dropdown";
import Button from "primevue/button";

import AppFormSection from "./AppFormSection.vue";
import AppFormGrid from "./AppFormGrid.vue";
import AppFormField from "./AppFormField.vue";
import AppIcon from "../AppIcon.vue";

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  /** Erros por campo do endereço: { cep, street, ... }. */
  errors: { type: Object, default: () => ({}) },
  readonly: { type: Boolean, default: false },
  required: { type: Boolean, default: false },
  description: { type: String, default: "" },
  /** Habilita busca automática por CEP (ViaCEP). */
  autoFill: { type: Boolean, default: true },
});

const emit = defineEmits(["update:modelValue"]);

const UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"];

const model = computed(() => props.modelValue || {});
const looking = ref(false);
const lookupError = ref("");
let lastLookedUp = "";

function set(key, value) {
  emit("update:modelValue", { ...model.value, [key]: value });
}

/** Aplica máscara 00000-000 conforme o usuário digita. */
function onCepInput(raw) {
  const digits = String(raw || "").replace(/\D/g, "").slice(0, 8);
  const masked = digits.length > 5 ? `${digits.slice(0, 5)}-${digits.slice(5)}` : digits;
  set("cep", masked);
}

function cepDigits() {
  return String(model.value.cep || "").replace(/\D/g, "");
}

function maybeLookup() {
  if (!props.autoFill || props.readonly) return;
  if (cepDigits().length === 8 && cepDigits() !== lastLookedUp) lookup();
}

/** Busca no ViaCEP. Falha do provedor não interrompe o cadastro (STC-041). */
async function lookup() {
  const cep = cepDigits();
  if (cep.length !== 8) {
    lookupError.value = "Informe um CEP com 8 dígitos.";
    return;
  }
  looking.value = true;
  lookupError.value = "";
  lastLookedUp = cep;
  try {
    const res = await window.fetch(`https://viacep.com.br/ws/${cep}/json/`);
    const data = await res.json();
    if (data.erro) {
      lookupError.value = "CEP não encontrado. Preencha manualmente.";
      return;
    }
    emit("update:modelValue", {
      ...model.value,
      street: data.logradouro || model.value.street || "",
      district: data.bairro || model.value.district || "",
      city: data.localidade || model.value.city || "",
      state: data.uf || model.value.state || "",
    });
  } catch {
    lookupError.value = "Não foi possível consultar o CEP agora. Preencha manualmente.";
  } finally {
    looking.value = false;
  }
}
</script>

<style scoped>
.appaddr__cep { display: flex; align-items: center; gap: 4px; }
.appaddr__cep :deep(.p-inputtext) { flex: 1; }
.appaddr__hint { display: flex; align-items: center; gap: 6px; color: var(--text-muted); font: var(--weight-medium) 12px/1.3 var(--font-sans); }
</style>
