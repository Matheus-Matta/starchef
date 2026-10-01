<template>
  <AppEntityDialog
    :visible="visible"
    title="Excluir pedidos"
    :save-label="`Excluir ${ids.length} ${ids.length === 1 ? 'pedido' : 'pedidos'}`"
    cancel-label="Voltar"
    :saving="loading"
    width="520px"
    @update:visible="emit('update:visible', $event)"
    @save="excluir"
  >
    <Message severity="info" :closable="false" class="bulkmsg">
      <p class="bulkmsg__texto">
        Só são excluídos os pedidos <strong>sem nota fiscal e sem pagamento recebido</strong> — por exemplo,
        pedidos abertos vazios ou cancelados que nunca foram pagos. Pedido com nota ou com pagamento é venda:
        use <strong>Cancelar pedidos</strong>.
      </p>
    </Message>
  </AppEntityDialog>
</template>

<script setup>
import { computed, ref } from "vue";
import Message from "primevue/message";
import { useToast } from "primevue/usetoast";

import AppEntityDialog from "../form/AppEntityDialog.vue";
import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";
import { resumoDoLote } from "./orderBulkSummary";

const props = defineProps({
  visible: { type: Boolean, default: false },
  selection: { type: Array, required: true },
});
const emit = defineEmits(["completed", "update:visible"]);
const toast = useToast();
const loading = ref(false);

const ids = computed(() => props.selection.map((row) => row.id).filter(Boolean));

async function excluir() {
  loading.value = true;
  try {
    const { data } = await api.post("/orders/bulk-delete/", { ids: ids.value }, { skipRestaurantScope: true });
    toast.add(resumoDoLote(data.deleted, "excluído(s)", data.skipped));
    emit("update:visible", false);
    emit("completed");
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível excluir", detail: normalizeApiError(error).message, life: 6000 });
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.bulkmsg { margin: 0; }
.bulkmsg__texto { margin: 0; font: var(--weight-medium) 13px/1.45 var(--font-sans); }
</style>
