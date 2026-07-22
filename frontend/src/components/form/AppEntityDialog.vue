<template>
  <Dialog
    :visible="visible"
    :header="resolvedTitle"
    :modal="true"
    :draggable="false"
    :dismissable-mask="false"
    :close-on-escape="!saving"
    :style="{ width: width }"
    :breakpoints="{ '640px': '96vw' }"
    class="appdialog"
    @update:visible="onVisibleChange"
  >
    <div class="appdialog__body">
      <slot />
    </div>

    <template #footer>
      <div class="appdialog__footer">
        <slot name="footer-start" />
        <div class="appdialog__footer-actions">
          <Button
            type="button"
            :label="cancelLabel"
            severity="secondary"
            outlined
            :disabled="saving"
            @click="requestClose"
          />
          <Button
            type="button"
            :label="resolvedSaveLabel"
            icon="pi pi-check"
            :loading="saving"
            @click="$emit('save')"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
/**
 * Diálogo padrão para criar/editar entidades em modal (Sprint 0 · STC-005).
 * Fornece cabeçalho por modo, rodapé com Cancelar/Salvar, estado de salvamento
 * e confirmação ao fechar com alterações não salvas (`dirty`).
 *
 * Uso:
 *   <AppEntityDialog v-model:visible="open" entity="Adicional" :mode="mode"
 *                    :saving="saving" :dirty="dirty" @save="submit">
 *     ...campos...
 *   </AppEntityDialog>
 */
import { computed } from "vue";
import Dialog from "primevue/dialog";
import Button from "primevue/button";
import { useConfirm } from "primevue/useconfirm";

const props = defineProps({
  visible: { type: Boolean, default: false },
  /** Nome da entidade — usado para montar títulos padrão ("Novo X" / "Editar X"). */
  entity: { type: String, default: "registro" },
  /** Título explícito; sobrepõe o título derivado de entity/mode. */
  title: { type: String, default: "" },
  mode: { type: String, default: "create" }, // "create" | "edit"
  saving: { type: Boolean, default: false },
  /** Há alterações não salvas? Dispara confirmação ao fechar. */
  dirty: { type: Boolean, default: false },
  saveLabel: { type: String, default: "" },
  cancelLabel: { type: String, default: "Cancelar" },
  width: { type: String, default: "560px" },
});

const emit = defineEmits(["update:visible", "save", "cancel"]);
const confirm = useConfirm();

const isEdit = computed(() => props.mode === "edit");
const resolvedTitle = computed(() => props.title || `${isEdit.value ? "Editar" : "Novo"} ${props.entity}`);
const resolvedSaveLabel = computed(() => props.saveLabel || (isEdit.value ? "Salvar alterações" : "Adicionar"));

function close() {
  emit("update:visible", false);
  emit("cancel");
}

function requestClose() {
  if (!props.dirty) {
    close();
    return;
  }
  confirm.require({
    message: "Há alterações não salvas. Deseja descartá-las?",
    header: "Descartar alterações?",
    icon: "pi pi-exclamation-triangle",
    acceptLabel: "Descartar",
    rejectLabel: "Continuar editando",
    acceptClass: "p-button-danger",
    accept: close,
  });
}

/** PrimeVue emite update:visible=false ao clicar no X/máscara/Esc. */
function onVisibleChange(value) {
  if (value) {
    emit("update:visible", true);
  } else {
    requestClose();
  }
}
</script>

<style scoped>
.appdialog__body { display: flex; flex-direction: column; gap: var(--space-4); }
.appdialog__footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; }
.appdialog__footer-actions { display: flex; align-items: center; gap: 8px; margin-left: auto; }
</style>
