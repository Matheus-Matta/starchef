<template>
  <Dialog
    :visible="visible"
    modal
    header="Registrar divergência de vendas"
    :closable="!saving"
    :style="{ width: 'min(560px, calc(100vw - 28px))' }"
    @update:visible="close"
  >
    <div class="discrepancy-form">
      <Message severity="info" :closable="false">
        Registre o valor que entrou no caixa <b>sem venda no PDV</b>, por forma de pagamento.
        Isto não cria pedido nem NFC-e: a regularização fiscal é decidida com o contador.
      </Message>
      <div v-if="loadingMethods" class="discrepancy-form__state">Carregando formas de pagamento...</div>
      <div v-else class="discrepancy-form__methods">
        <label v-for="method in methods" :key="method.id" class="discrepancy-form__method">
          <span>{{ method.name }}</span>
          <InputNumber
            v-model="amounts[method.id]"
            mode="currency"
            currency="BRL"
            locale="pt-BR"
            :min="0"
            :input-id="`discrepancy-${method.id}`"
            :aria-label="`Valor em ${method.name}`"
          />
        </label>
      </div>
      <div class="discrepancy-form__total"><span>Total da divergência</span><strong>{{ centsToMoney(total) }}</strong></div>
      <div class="discrepancy-form__field">
        <label for="discrepancy-reason">Motivo</label>
        <Textarea id="discrepancy-reason" v-model="reason" rows="2" auto-resize placeholder="Ex.: movimento alto, vendas realizadas sem lançamento no sistema." />
      </div>
      <div class="discrepancy-form__field">
        <label for="discrepancy-notes">Observação (opcional)</label>
        <Textarea id="discrepancy-notes" v-model="notes" rows="2" auto-resize />
      </div>
      <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
      <div class="discrepancy-form__actions">
        <Button label="Cancelar" severity="secondary" outlined :disabled="saving" @click="close(false)" />
        <Button label="Registrar divergência" icon="pi pi-check" :loading="saving" :disabled="!canSubmit" @click="submit" />
      </div>
    </div>
  </Dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import Button from "primevue/button";
import Dialog from "primevue/dialog";
import InputNumber from "primevue/inputnumber";
import Message from "primevue/message";
import Textarea from "primevue/textarea";

import { api } from "../../services/api";
import { buildPayload, centsToMoney, registerDiscrepancy, totalInCents } from "../../services/cashDiscrepancies";
import { normalizeApiError } from "../../utils/apiError";

const props = defineProps({ visible: Boolean, cashRegister: { type: String, default: "" } });
const emit = defineEmits(["update:visible", "saved"]);

const methods = ref([]), loadingMethods = ref(false), saving = ref(false), error = ref("");
const amounts = reactive({}), reason = ref(""), notes = ref("");
const total = computed(() => totalInCents(amounts));
const canSubmit = computed(() => total.value > 0 && reason.value.trim().length > 0 && !saving.value);

function reset() {
  Object.keys(amounts).forEach((key) => delete amounts[key]);
  reason.value = "";
  notes.value = "";
  error.value = "";
}

async function loadMethods() {
  loadingMethods.value = true;
  try {
    const { data } = await api.get("/payments/methods/", { params: { is_active: true, page_size: 100 } });
    methods.value = data.results || data;
  } catch (cause) {
    error.value = normalizeApiError(cause).message;
  } finally {
    loadingMethods.value = false;
  }
}

watch(() => props.visible, (open) => {
  if (!open) return;
  reset();
  if (!methods.value.length) loadMethods();
}, { immediate: true });

function close(value) {
  if (saving.value) return;
  emit("update:visible", Boolean(value));
}

async function submit() {
  if (!canSubmit.value) return;
  saving.value = true;
  error.value = "";
  try {
    const { data } = await registerDiscrepancy(
      buildPayload({ cashRegister: props.cashRegister, amounts, reason: reason.value, notes: notes.value }),
    );
    emit("saved", data);
    emit("update:visible", false);
  } catch (cause) {
    error.value = normalizeApiError(cause).message;
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.discrepancy-form{display:flex;flex-direction:column;gap:var(--section-content-gap)}
.discrepancy-form__methods{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.discrepancy-form__method,.discrepancy-form__field{display:flex;flex-direction:column;gap:6px}
.discrepancy-form__method span,.discrepancy-form__field label{font-weight:600;color:var(--text-strong)}
.discrepancy-form__method :deep(.p-inputnumber),.discrepancy-form__field :deep(.p-inputtextarea){width:100%}
.discrepancy-form__total{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border:1px solid var(--border);border-radius:var(--radius-md);background:var(--surface-ground)}
.discrepancy-form__total strong{font-size:18px;color:var(--text-strong)}
.discrepancy-form__state{color:var(--text-muted)}
.discrepancy-form__actions{display:flex;justify-content:flex-end;gap:10px;flex-wrap:wrap}
</style>
