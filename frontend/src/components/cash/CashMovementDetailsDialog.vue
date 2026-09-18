<template>
  <Dialog
    :visible="visible"
    modal
    header="Detalhes da movimentação"
    :style="{ width: 'min(560px, calc(100vw - 28px))' }"
    @update:visible="emit('update:visible', $event)"
  >
    <div v-if="movement" class="movement-detail">
      <div class="movement-detail__hero">
        <div><small>{{ dateTime(movement.created_at) }}</small><h3>{{ movementLabel }}</h3></div>
        <strong>{{ money(movement.amount) }}</strong>
      </div>
      <div class="movement-detail__grid">
        <div><small>Status</small><Tag :value="statusLabel" :severity="statusTone" /></div>
        <div><small>Saldo após</small><b>{{ nullableMoney(movement.balance_after) }}</b></div>
        <div><small>Caixa</small><b>{{ movement.cash_station_name || '—' }}</b></div>
        <div><small>Sessão</small><b>{{ shortId(movement.cash_register) }}</b></div>
        <div><small>Operador</small><b>{{ movement.operator_name || '—' }}</b></div>
        <div><small>Terminal</small><b>{{ movement.terminal_label || '—' }}</b></div>
        <div><small>Autorização</small><b>{{ authorizationLabel }}</b></div>
        <div><small>Autorizado por</small><b>{{ movement.authorized_by_name || '—' }}</b></div>
        <div><small>Pedido</small><b>{{ orderLabel }}</b></div>
        <div><small>Forma de pagamento</small><b>{{ movement.payment_method_name || '—' }}</b></div>
      </div>
      <div class="movement-detail__notes"><small>Motivo</small><p>{{ movement.reason || 'Não informado.' }}</p></div>
      <div class="movement-detail__notes"><small>Destino/origem</small><p>{{ movement.destination || 'Não informado.' }}</p></div>
      <div v-if="movement.manager_reason" class="movement-detail__notes"><small>Justificativa gerencial</small><p>{{ movement.manager_reason }}</p></div>
      <div class="movement-detail__actions">
        <Button v-if="movement.cash_register" label="Ver sessão completa" icon="pi pi-external-link" text @click="emit('view-session', movement.cash_register)" />
        <Button label="Fechar" severity="secondary" outlined @click="emit('update:visible', false)" />
      </div>
    </div>
  </Dialog>
</template>

<script setup>
import { computed } from "vue";
import Button from "primevue/button";
import Dialog from "primevue/dialog";
import Tag from "primevue/tag";

const props = defineProps({
  visible: { type: Boolean, default: false },
  movement: { type: Object, default: null },
});
const emit = defineEmits(["update:visible", "view-session"]);

const TYPES = { opening: "Abertura", sale: "Venda em dinheiro", withdrawal: "Sangria", supply: "Suprimento", closing: "Fechamento", adjustment: "Ajuste", refund: "Estorno" };
const AUTH = { pending: "Pendente", cash_password: "Senha do caixa", manager: "Gerente", automatic: "Automática" };
const movementLabel = computed(() => TYPES[props.movement?.movement_type] || props.movement?.movement_type || "Movimentação");
const authorizationLabel = computed(() => AUTH[props.movement?.authorization] || props.movement?.authorization || "—");
const statusLabel = computed(() => ({ pending: "Pendente", approved: "Confirmada", cancelled: "Cancelada" }[props.movement?.status] || props.movement?.status || "—"));
const statusTone = computed(() => ({ pending: "warning", approved: "success", cancelled: "danger" }[props.movement?.status] || "info"));
const orderLabel = computed(() => props.movement?.order_sequence ? `#${props.movement.order_sequence}` : "—");
const money = (value) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const nullableMoney = (value) => value === null || value === undefined ? "—" : money(value);
const dateTime = (value) => value ? new Date(value).toLocaleString("pt-BR") : "—";
const shortId = (value) => value ? String(value).slice(0, 8) : "—";
</script>

<style scoped>
.movement-detail{display:flex;flex-direction:column;gap:16px}
.movement-detail__hero{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:16px;border-radius:var(--radius-md);background:var(--surface-sunken)}
.movement-detail__hero div{display:flex;flex-direction:column;gap:4px}.movement-detail__hero h3{margin:0;color:var(--text-strong)}
.movement-detail__hero small,.movement-detail__grid small,.movement-detail__notes small{color:var(--text-muted);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
.movement-detail__hero>strong{color:var(--text-strong);font-size:22px;white-space:nowrap}
.movement-detail__grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.movement-detail__grid>div,.movement-detail__notes{display:flex;flex-direction:column;gap:5px;padding:12px;border:1px solid var(--border-subtle);border-radius:var(--radius-md)}
.movement-detail__grid b{color:var(--text-body);overflow-wrap:anywhere}.movement-detail__notes p{margin:0;color:var(--text-body);white-space:pre-wrap}
.movement-detail__actions{display:flex;justify-content:flex-end;gap:8px}
@media(max-width:560px){.movement-detail__grid{grid-template-columns:1fr}.movement-detail__hero{align-items:stretch;flex-direction:column}.movement-detail__actions{flex-direction:column}}
</style>
