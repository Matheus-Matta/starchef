<template>
  <button class="rpro-btn rpro-btn--ghost rpro-btn--sm" type="button" :disabled="loading" @click="confirmResend">
    <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-send'" /> Reenviar NFC-e
  </button>
</template>

<script setup>
import { ref } from "vue";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";

import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";

const props = defineProps({ selection: { type: Array, required: true } });
const emit = defineEmits(["completed"]);
const confirm = useConfirm();
const toast = useToast();
const loading = ref(false);

function confirmResend() {
  const issued = props.selection.filter((row) => row.status === "issued").length;
  confirm.require({
    message: `Reenviar as notas selecionadas?${issued ? ` ${issued} nota(s) já emitida(s) serão ignoradas.` : ""}`,
    header: "Confirmar reenvio em massa",
    icon: "pi pi-send",
    acceptLabel: "Reenviar",
    rejectLabel: "Cancelar",
    accept: resend,
  });
}

async function resend() {
  const ids = props.selection.map((row) => row.id);
  if (!ids.length) return;
  loading.value = true;
  try {
    const { data } = await api.post("/invoices/bulk-resend/", { ids }, { skipRestaurantScope: true });
    const details = [`${data.resent || 0} reenviada(s)`];
    if (data.skipped_issued) details.push(`${data.skipped_issued} já emitida(s) ignorada(s)`);
    if (data.skipped_cancelled) details.push(`${data.skipped_cancelled} cancelada(s) ignorada(s)`);
    if (data.failed) details.push(`${data.failed} com falha`);
    toast.add({
      severity: data.failed ? "warn" : "success",
      summary: "Reenvio em massa concluido",
      detail: `${details.join(", ")}.`,
      life: 6000,
    });
    emit("completed");
  } catch (error) {
    toast.add({
      severity: "error",
      summary: "Não foi possível reenviar as notas",
      detail: normalizeApiError(error).message,
      life: 5000,
    });
  } finally {
    loading.value = false;
  }
}
</script>
