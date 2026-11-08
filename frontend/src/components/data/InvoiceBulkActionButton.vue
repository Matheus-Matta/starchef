<template>
  <button class="rpro-btn rpro-btn--ghost rpro-btn--sm" type="button" :disabled="loading" @click="confirmRun">
    <i :class="loading ? 'pi pi-spin pi-spinner' : action.icon" /> {{ action.label }}
  </button>
</template>

<script setup>
import { ref } from "vue";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";
import { bulkJobToast } from "./bulkJobToast";

// `action` vem de `invoiceProConfig.bulkActions`: rota, textos e ícone. O
// botão é um só para reenviar e recriar — o que muda é o que o worker faz.
const props = defineProps({
  selection: { type: Array, required: true },
  action: { type: Object, required: true },
});
const emit = defineEmits(["completed"]);
const confirm = useConfirm();
const toast = useToast();
const loading = ref(false);

function confirmRun() {
  const issued = props.selection.filter((row) => row.status === "issued").length;
  confirm.require({
    message: `${props.action.confirmMessage}${issued ? ` ${issued} nota(s) já emitida(s) serão ignoradas.` : ""}`,
    header: props.action.confirmHeader,
    icon: props.action.icon,
    acceptLabel: props.action.acceptLabel,
    rejectLabel: "Cancelar",
    accept: run,
  });
}

async function run() {
  const ids = props.selection.map((row) => row.id);
  if (!ids.length) return;
  loading.value = true;
  try {
    const { data } = await api.post(props.action.endpoint, { ids }, { skipRestaurantScope: true });
    toast.add(bulkJobToast(data, "notas"));
    emit("completed");
  } catch (error) {
    toast.add({
      severity: "error",
      summary: props.action.errorSummary,
      detail: normalizeApiError(error).message,
      life: 5000,
    });
  } finally {
    loading.value = false;
  }
}
</script>
