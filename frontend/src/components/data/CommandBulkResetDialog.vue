<template>
  <AppEntityDialog
    :visible="visible"
    title="Zerar comandas"
    :save-label="`Zerar ${ids.length} ${ids.length === 1 ? 'comanda' : 'comandas'}`"
    cancel-label="Voltar"
    :saving="loading"
    :dirty="!!reason.trim()"
    width="520px"
    @update:visible="emit('update:visible', $event)"
    @save="zerar"
  >
    <Message severity="warn" :closable="false" class="bulkmsg">
      <p class="bulkmsg__texto">
        Os itens ainda abertos saem das comandas como cancelados e os cartões voltam livres. Nada é apagado: os itens
        continuam no histórico de cada comanda, com este motivo. A cozinha só é avisada do que ainda está em produção.
      </p>
    </Message>
    <AppFormGrid :columns="1">
      <AppFormField v-slot="{ fieldId, invalid }" label="Motivo" name="reason" required full :error="erroMotivo">
        <Textarea :id="fieldId" v-model="reason" rows="3" auto-resize maxlength="255" :invalid="invalid" class="w-full" />
      </AppFormField>
      <AppFormField
        v-slot="{ fieldId }"
        label="Senha de operação do restaurante"
        name="cash_password"
        full
        help="Sem a senha, comandas com item fora do prazo de cancelamento ficam como estão e aparecem no resumo."
      >
        <Password v-model="password" :input-id="fieldId" :feedback="false" toggle-mask class="w-full" input-class="w-full" />
      </AppFormField>
    </AppFormGrid>
  </AppEntityDialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import Message from "primevue/message";
import Password from "primevue/password";
import Textarea from "primevue/textarea";
import { useToast } from "primevue/usetoast";

import AppEntityDialog from "../form/AppEntityDialog.vue";
import AppFormField from "../form/AppFormField.vue";
import AppFormGrid from "../form/AppFormGrid.vue";
import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";
import { resumoDoZeramento } from "./commandResetSummary";

const props = defineProps({
  visible: { type: Boolean, default: false },
  selection: { type: Array, required: true },
});
const emit = defineEmits(["completed", "update:visible"]);
const toast = useToast();
const loading = ref(false);
const reason = ref("");
const password = ref("");
const erroMotivo = ref("");

const ids = computed(() => [...new Set(props.selection.map((row) => row.id).filter(Boolean))]);

// Cada abertura começa limpa: motivo e senha de um lote não vazam para o próximo.
watch(
  () => props.visible,
  (aberto) => {
    if (!aberto) return;
    reason.value = "";
    password.value = "";
    erroMotivo.value = "";
  },
);

async function zerar() {
  if (!reason.value.trim()) {
    erroMotivo.value = "Informe o motivo para zerar as comandas.";
    return;
  }
  loading.value = true;
  try {
    const { data } = await api.post("/commands/bulk-reset/", {
      ids: ids.value,
      reason: reason.value.trim(),
      cash_password: password.value,
    });
    toast.add(resumoDoZeramento(data.reset, data.skipped));
    emit("update:visible", false);
    emit("completed");
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível zerar", detail: normalizeApiError(error).message, life: 6000 });
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.bulkmsg { margin: 0; }
.bulkmsg__texto { margin: 0; font: var(--weight-medium) 13px/1.45 var(--font-sans); }
</style>
