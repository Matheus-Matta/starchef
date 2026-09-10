<template>
  <AppEntityDialog
    :visible="visible"
    entity="variação"
    :mode="editing.id ? 'edit' : 'create'"
    :saving="saving"
    :dirty="dirty"
    width="640px"
    @update:visible="$emit('update:visible', $event)"
    @save="$emit('save')"
  >
    <AppErrorSummary :message="formError" />
    <AppFormGrid :columns="2">
      <AppFormField label="Nome" name="name" :error="fieldErrors.name" required full>
        <template #default="{ fieldId, invalid }">
          <InputText :id="fieldId" :model-value="editing.name" :class="{ 'p-invalid': invalid }" placeholder="Ex.: Grande, Sem cebola" @update:model-value="update('name', $event)" />
        </template>
      </AppFormField>
      <AppFormField label="Ajuste de preço (R$)" name="price_delta" :error="fieldErrors.price_delta" help="Use valores negativos para desconto.">
        <template #default="{ fieldId, invalid }">
          <InputNumber :id="fieldId" :model-value="editing.price_delta" :class="{ 'p-invalid': invalid }" mode="currency" currency="BRL" locale="pt-BR" :min-fraction-digits="2" @update:model-value="update('price_delta', $event)" />
        </template>
      </AppFormField>
      <AppFormField label="Ativa">
        <div class="variation-dialog__switch">
          <InputSwitch :model-value="editing.is_active" @update:model-value="update('is_active', $event)" />
          <span>{{ editing.is_active ? "Ativa" : "Inativa" }}</span>
        </div>
      </AppFormField>
      <AppFormField label="Imagem da variação" name="logo_image" :error="fieldErrors.logo_image" help="Escolha uma foto da galeria do produto." full>
        <template #default="{ fieldId, invalid }">
          <div :id="fieldId" :class="['variation-dialog__images', { 'p-invalid': invalid }]" role="radiogroup">
            <button
              type="button"
              :class="['variation-dialog__inherit', { 'is-selected': !editing.logo_image }]"
              :aria-pressed="!editing.logo_image"
              @click="update('logo_image', null)"
            >
              <i class="pi pi-ban" />
              <span>Sem imagem</span>
            </button>
            <button
              v-for="option in imageOptions"
              :key="option.value"
              type="button"
              :class="['variation-dialog__image', { 'is-selected': editing.logo_image === option.value }]"
              :aria-label="`Selecionar ${option.label}`"
              :aria-pressed="editing.logo_image === option.value"
              @click="update('logo_image', option.value)"
            >
              <img :src="option.url" :alt="option.label" />
              <span>{{ option.label }}</span>
              <i v-if="editing.logo_image === option.value" class="pi pi-check" />
            </button>
          </div>
          <small class="variation-dialog__count">{{ imageOptions.length }} fotos disponíveis</small>
        </template>
      </AppFormField>
    </AppFormGrid>
  </AppEntityDialog>
</template>

<script setup>
import InputNumber from "primevue/inputnumber";
import InputSwitch from "primevue/inputswitch";
import InputText from "primevue/inputtext";
import AppEntityDialog from "../form/AppEntityDialog.vue";
import AppErrorSummary from "../form/AppErrorSummary.vue";
import AppFormField from "../form/AppFormField.vue";
import AppFormGrid from "../form/AppFormGrid.vue";

const props = defineProps({
  visible: { type: Boolean, default: false },
  editing: { type: Object, required: true },
  saving: { type: Boolean, default: false },
  dirty: { type: Boolean, default: false },
  formError: { type: String, default: "" },
  fieldErrors: { type: Object, default: () => ({}) },
  imageOptions: { type: Array, default: () => [] },
});
const emit = defineEmits(["update:visible", "update:editing", "save", "dirty"]);

function update(field, value) {
  emit("update:editing", { ...props.editing, [field]: value });
  emit("dirty");
}
</script>

<style scoped>
.variation-dialog__switch { display: flex; align-items: center; gap: 10px; height: var(--control-h); }
.variation-dialog__images { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 10px; }
.variation-dialog__image, .variation-dialog__inherit {
  position: relative; display: grid; min-width: 0; gap: 6px; padding: 7px;
  border: 2px solid var(--border); border-radius: var(--radius-md);
  color: var(--text-muted); background: var(--surface-card); cursor: pointer;
}
.variation-dialog__image:hover, .variation-dialog__inherit:hover { border-color: var(--primary); }
.variation-dialog__image.is-selected, .variation-dialog__inherit.is-selected {
  border-color: var(--primary); box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 18%, transparent);
}
.variation-dialog__image img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; }
.variation-dialog__image span { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.variation-dialog__image > .pi-check { position: absolute; top: 12px; right: 12px; padding: 5px; border-radius: 50%; color: white; background: var(--primary); }
.variation-dialog__inherit { min-height: 110px; place-content: center; justify-items: center; }
.variation-dialog__inherit > .pi { font-size: 28px; }
.variation-dialog__inherit span { font-size: 12px; }
.variation-dialog__count { display: block; margin-top: 8px; color: var(--text-muted); }
</style>
