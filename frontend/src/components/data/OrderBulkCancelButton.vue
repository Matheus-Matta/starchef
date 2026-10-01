<template>
  <button class="rpro-btn rpro-btn--ghost rpro-btn--sm" type="button" :disabled="loading" @click="abrir">
    <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-times-circle'" /> {{ label }} ({{ ids.length }})
  </button>
  <Dialog v-model:visible="visible" modal :header="label" :style="{ width: 'min(480px, 94vw)' }">
    <p class="mb-3">
      Cancelar <strong>{{ ids.length }}</strong> pedido(s)? A nota fiscal, os pagamentos e o caixa de cada um
      também são cancelados — é o mesmo que cancelar um por um.
    </p>
    <label class="block text-sm mb-1" for="bulk-cancel-reason">Motivo (obrigatório)</label>
    <InputText id="bulk-cancel-reason" v-model="reason" class="w-full mb-3" maxlength="255" autofocus />
    <label class="block text-sm mb-1" for="bulk-cancel-password">Senha de operação do restaurante</label>
    <Password id="bulk-cancel-password" v-model="password" :feedback="false" toggle-mask class="w-full" input-class="w-full" />
    <small class="block text-muted mt-1">
      Sem a senha, só saem os pedidos vazios ou ainda dentro do prazo de carência.
    </small>
    <template #footer>
      <button class="rpro-btn rpro-btn--ghost" type="button" @click="visible = false">Voltar</button>
      <button class="rpro-btn rpro-btn--primary" type="button" :disabled="!reason.trim() || loading" @click="cancelar">
        <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-times-circle'" /> Cancelar pedidos
      </button>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, ref } from "vue";
import Dialog from "primevue/dialog";
import InputText from "primevue/inputtext";
import Password from "primevue/password";
import { useToast } from "primevue/usetoast";

import { api } from "../../services/api";
import { normalizeApiError } from "../../utils/apiError";

// `idField` é "order" na lista de notas fiscais: a nota cancela pelo pedido
// dela, e o cancelamento do pedido já cancela a nota.
const props = defineProps({
  selection: { type: Array, required: true },
  idField: { type: String, default: "id" },
  label: { type: String, default: "Cancelar pedidos" },
});
const emit = defineEmits(["completed"]);
const toast = useToast();
const visible = ref(false);
const loading = ref(false);
const reason = ref("");
const password = ref("");

const ids = computed(() => [...new Set(props.selection.map((row) => row[props.idField]).filter(Boolean))]);

function abrir() {
  reason.value = "";
  password.value = "";
  visible.value = true;
}

async function cancelar() {
  loading.value = true;
  try {
    const { data } = await api.post(
      "/orders/bulk-cancel/",
      { ids: ids.value, reason: reason.value.trim(), cash_password: password.value },
      { skipRestaurantScope: true },
    );
    const pulados = data.skipped || [];
    toast.add({
      severity: pulados.length ? "warn" : "success",
      summary: `${data.cancelled || 0} pedido(s) cancelado(s)`,
      detail: pulados.length
        ? `${pulados.length} ficaram de fora: ${pulados.slice(0, 3).map((p) => `#${p.sequence} (${p.reason})`).join(", ")}`
        : undefined,
      life: 8000,
    });
    visible.value = false;
    emit("completed");
  } catch (error) {
    toast.add({ severity: "error", summary: "Não foi possível cancelar", detail: normalizeApiError(error).message, life: 6000 });
  } finally {
    loading.value = false;
  }
}
</script>
