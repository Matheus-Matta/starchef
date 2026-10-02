<template>
  <div class="discrepancy-list">
    <p v-if="!items.length" class="discrepancy-list__empty">Nenhuma divergência registrada.</p>
    <article v-for="item in items" :key="item.id" :class="['discrepancy-list__item', { 'is-cancelled': item.status === 'cancelled' }]">
      <header>
        <div>
          <strong>{{ money(item.amount) }}</strong>
          <Tag :value="statusLabel(item.status)" :severity="statusTone(item.status)" />
        </div>
        <small>{{ dateTime(item.created_at) }} · {{ item.created_by_name || '—' }}</small>
      </header>
      <ul class="discrepancy-list__methods">
        <li v-for="method in item.payment_methods" :key="method.payment_method">{{ method.name }}: <b>{{ money(method.amount) }}</b></li>
      </ul>
      <p><small>Motivo:</small> {{ item.reason }}</p>
      <p v-if="item.notes"><small>Observação:</small> {{ item.notes }}</p>
      <p v-if="item.regularization_note"><small>Regularização:</small> {{ item.regularization_note }}</p>
      <p v-if="item.cancel_reason"><small>Cancelada:</small> {{ item.cancel_reason }}</p>
      <div v-if="canDecide && availableDecisions(item.status).length" class="discrepancy-list__actions screen-only">
        <Button
          v-for="decision in availableDecisions(item.status)"
          :key="decision"
          :label="DECISIONS[decision].button"
          :severity="decision === 'cancel' ? 'danger' : decision === 'regularize' ? 'success' : 'secondary'"
          size="small"
          outlined
          @click="openDecision(item, decision)"
        />
      </div>
    </article>

    <Dialog v-model:visible="decisionVisible" modal :header="current ? DECISIONS[current.decision].title : ''" :closable="!saving" :style="{ width: 'min(480px, calc(100vw - 28px))' }">
      <div v-if="current" class="discrepancy-list__decision">
        <p>Divergência de <b>{{ money(current.item.amount) }}</b>.</p>
        <div v-if="DECISIONS[current.decision].field" class="discrepancy-list__field">
          <label for="discrepancy-decision-text">{{ DECISIONS[current.decision].label }}</label>
          <Textarea id="discrepancy-decision-text" v-model="text" rows="3" auto-resize :placeholder="DECISIONS[current.decision].placeholder" />
        </div>
        <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
        <div class="discrepancy-list__actions">
          <Button label="Voltar" severity="secondary" outlined :disabled="saving" @click="decisionVisible = false" />
          <Button :label="DECISIONS[current.decision].button" :loading="saving" :disabled="needsText && !text.trim()" @click="confirm" />
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import Button from "primevue/button";
import Dialog from "primevue/dialog";
import Message from "primevue/message";
import Tag from "primevue/tag";
import Textarea from "primevue/textarea";

import { DECISIONS, availableDecisions, decide, statusLabel, statusTone } from "../../services/cashDiscrepancies";
import { normalizeApiError } from "../../utils/apiError";

defineProps({ items: { type: Array, default: () => [] }, canDecide: { type: Boolean, default: true } });
const emit = defineEmits(["changed"]);

const decisionVisible = ref(false), current = ref(null), text = ref(""), saving = ref(false), error = ref("");
const needsText = computed(() => Boolean(current.value && DECISIONS[current.value.decision].field));
const money = (value) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const dateTime = (value) => (value ? new Date(value).toLocaleString("pt-BR") : "—");

function openDecision(item, decision) {
  current.value = { item, decision };
  text.value = "";
  error.value = "";
  decisionVisible.value = true;
}

async function confirm() {
  const { item, decision } = current.value;
  const field = DECISIONS[decision].field;
  saving.value = true;
  error.value = "";
  try {
    const { data } = await decide(item.id, decision, field ? { [field]: text.value.trim() } : {});
    decisionVisible.value = false;
    emit("changed", data);
  } catch (cause) {
    // 409: outro gerente decidiu antes. A lista é recarregada para mostrar o
    // estado de verdade, e o recado explica por que nada mudou aqui.
    error.value = normalizeApiError(cause).message;
    if (cause?.response?.status === 409) emit("changed", null);
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.discrepancy-list{display:flex;flex-direction:column;gap:10px}
.discrepancy-list__empty{margin:0;color:var(--text-muted)}
.discrepancy-list__item{display:flex;flex-direction:column;gap:6px;padding:12px 14px;border:1px solid var(--border);border-left:3px solid var(--warning);border-radius:var(--radius-md)}
.discrepancy-list__item.is-cancelled{border-left-color:var(--border-strong);opacity:.75}
.discrepancy-list__item header{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.discrepancy-list__item header>div{display:flex;align-items:center;gap:8px}
.discrepancy-list__item p{margin:0}
.discrepancy-list__item small{color:var(--text-muted)}
.discrepancy-list__methods{margin:0;padding-left:18px;display:flex;flex-wrap:wrap;gap:4px 18px}
.discrepancy-list__actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}
.discrepancy-list__decision,.discrepancy-list__field{display:flex;flex-direction:column;gap:10px}
.discrepancy-list__field label{font-weight:600;color:var(--text-strong)}
.discrepancy-list__decision p{margin:0}
</style>
