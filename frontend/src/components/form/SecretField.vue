<template>
  <div class="secretfield">
    <div v-if="configured && !revealing" class="secretfield__masked">
      <InputText :model-value="MASK" disabled fluid />
      <Tag value="Salvo" severity="success" rounded />
      <Button type="button" label="Alterar" icon="pi pi-pencil" size="small" text @click="$emit('edit')" />
    </div>
    <Password
      v-else
      :model-value="modelValue"
      :placeholder="placeholder"
      :feedback="false"
      toggle-mask
      fluid
      input-class="secretfield__input"
      @update:model-value="$emit('update:modelValue', $event)"
    />
    <small class="secretfield__notice">
      <i class="pi pi-shield" aria-hidden="true" />
      Por segurança, um valor salvo não pode ser exibido novamente — só substituído por um novo.
    </small>
  </div>
</template>

<script setup>
/**
 * Campo de segredo (senha, token, CSC) que o backend nunca devolve em texto.
 *
 * O problema que resolve: um `<Password>` com valor vazio e só um placeholder
 * mascarado (`••••••••`) é visualmente idêntico a um campo realmente vazio —
 * o placeholder some ao focar, e nada mais indica que já existe um valor
 * salvo. Aqui, quando `configured` é true e o operador não pediu para trocar,
 * o campo mostra a máscara como VALOR de verdade (bloqueado, com o selo
 * "Salvo") em vez de placeholder; só depois de clicar em "Alterar" ele vira
 * editável para receber um valor novo.
 *
 * Quem decide se está em edição é o PAI (prop `revealing` + evento `edit`):
 * assim, ao recarregar a configuração do servidor, o pai reresetando esse
 * estado é o que evita o campo ficar preso em "editando" depois de salvar.
 */
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import Tag from "primevue/tag";

defineProps({
  modelValue: { type: String, default: "" },
  /** O backend já tem um valor salvo para este campo. */
  configured: { type: Boolean, default: false },
  /** O operador pediu para substituir o valor salvo (via evento `edit`). */
  revealing: { type: Boolean, default: false },
  placeholder: { type: String, default: "" },
});

defineEmits(["update:modelValue", "edit"]);

/** Nunca é o segredo real — é só a representação visual de "há um valor salvo". */
const MASK = "••••••••";
</script>

<style scoped>
.secretfield { display: flex; flex-direction: column; gap: 7px; min-width: 0; }

.secretfield__masked { display: flex; align-items: center; gap: 8px; min-width: 0; }
.secretfield__masked :deep(.p-inputtext) {
  min-width: 0;
  color: var(--text-muted);
  letter-spacing: 0.12em;
}

.secretfield__notice {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  color: var(--text-muted);
  font: var(--weight-medium) 11.5px/1.35 var(--font-sans);
}
.secretfield__notice i { margin-top: 1px; }

:deep(.p-password) { width: 100%; }
:deep(.p-password-input) { width: 100%; }
</style>
