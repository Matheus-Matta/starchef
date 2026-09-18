<template>
  <main class="cash-statement">
    <div v-if="loading" class="cash-statement__state">Carregando detalhamento da sessão...</div>
    <div v-else-if="error" class="cash-statement__state cash-statement__state--error">{{ error }}</div>
    <template v-else-if="session">
      <header class="cash-statement__header">
        <div><button class="cash-statement__back screen-only" type="button" @click="router.back()">← Voltar</button><small>EXTRATO DA SESSÃO</small><h1>{{ session.cash_station_name || 'Caixa' }}</h1><p>{{ holderLabel }}</p></div>
        <div class="cash-statement__actions screen-only"><Button label="Exportar CSV" icon="pi pi-download" severity="secondary" outlined @click="downloadCashSessionCsv(statement)" /><Button label="Imprimir" icon="pi pi-print" @click="printStatement" /></div>
      </header>

      <section class="cash-statement__identity">
        <div><small>Status</small><Tag :value="statusLabel(session.status)" :severity="statusTone(session.status)" /></div>
        <div><small>Operador</small><b>{{ session.opened_by_name || '—' }}</b></div>
        <div><small>Terminal de abertura</small><b>{{ session.terminal_label || '—' }}</b></div>
        <div><small>Abertura</small><b>{{ dateTime(session.opened_at) }}</b></div>
        <div><small>Fechamento</small><b>{{ dateTime(session.closed_at) }}</b></div>
        <div><small>Fechado por / terminal</small><b>{{ session.closed_by_name || '—' }} · {{ session.closed_terminal_label || '—' }}</b></div>
        <div><small>Observações</small><b>{{ session.notes || session.approval_reason || '—' }}</b></div>
      </section>

      <CashSessionSummary :session="session" />

      <Card v-if="occurrences.length" title="Ocorrências e falhas" subtitle="Pendências, cancelamentos e itens que exigem conferência">
        <ul class="cash-statement__issues"><li v-for="issue in occurrences" :key="issue.key"><Tag :value="issue.kind" :severity="issue.tone" /><span>{{ issue.text }}</span></li></ul>
      </Card>

      <Card title="Entradas, saídas e suprimentos" subtitle="Clique em uma movimentação para conferir todos os campos" padding="none">
        <ReportDataTable :rows="movementRows" :columns="movementColumns" row-clickable @row-click="openMovement" />
      </Card>

      <Card title="Recebimentos e formas de pagamento" subtitle="Todos os pagamentos vinculados a esta sessão" padding="none">
        <ReportDataTable :rows="saleRows" :columns="saleColumns" />
      </Card>

      <Card title="Pedidos da sessão" subtitle="Totais, taxas, descontos, responsáveis e eventuais cancelamentos" padding="none">
        <ReportDataTable :rows="orderRows" :columns="orderColumns" />
      </Card>

      <Card title="Itens dos pedidos" subtitle="Produtos, quantidades, valores, produção, observações e cancelamentos" padding="none">
        <ReportDataTable :rows="itemRows" :columns="itemColumns" />
      </Card>

      <CashMovementDetailsDialog v-model:visible="movementDialog" :movement="selectedMovement" />
    </template>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Tag from "primevue/tag";

import CashMovementDetailsDialog from "../components/cash/CashMovementDetailsDialog.vue";
import CashSessionSummary from "../components/cash/CashSessionSummary.vue";
import ReportDataTable from "../components/data/ReportDataTable.vue";
import Card from "../components/display/Card.vue";
import { api } from "../services/api";
import { downloadCashSessionCsv, printCashSessionStatement } from "../services/cashSessionExport";
import { normalizeApiError } from "../utils/apiError";

const route = useRoute(), router = useRouter();
const statement = ref({}), loading = ref(true), error = ref("");
const selectedMovement = ref(null), movementDialog = ref(false);
const session = computed(() => statement.value.session || null);
const money = (value) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const dateTime = (value) => value ? new Date(value).toLocaleString("pt-BR") : "—";
const TYPES = { opening: "Abertura", sale: "Venda em dinheiro", withdrawal: "Sangria", supply: "Suprimento", closing: "Fechamento", adjustment: "Ajuste", refund: "Estorno" };
const AUTH = { pending: "Pendente", cash_password: "Senha do caixa", manager: "Gerente", automatic: "Automática" };
const ORDER_TYPE = { table: "Mesa", command: "Comanda", counter: "Balcão", delivery: "Entrega", takeaway: "Retirada", internal: "Interno" };
const ORDER_STATUS = { open: "Aberto", awaiting_payment: "Aguardando pagamento", paid: "Pago", cancelled: "Cancelado", refunded: "Estornado" };
const PAYMENT_STATUS = { pending: "Pendente", partial: "Parcial", paid: "Pago", refunded: "Estornado" };
const ITEM_STATUS = { pending: "Pendente", queued: "Na fila", sent: "Enviado", preparing: "Em preparo", ready: "Pronto", delivered: "Entregue", cancelled: "Cancelado", comped: "Cortesia" };
const holderLabel = computed(() => `${session.value?.opened_by_name || 'Operador não identificado'} · ${session.value?.terminal_label || 'terminal não identificado'}`);
const statusLabel = (value) => ({ open: "Aberto", pending_manager_approval: "Aguardando aprovação", closed: "Fechado", closed_with_difference: "Fechado com diferença", cancelled: "Cancelado", blocked: "Bloqueado" }[value] || value);
const statusTone = (value) => ({ open: "success", closed: "info", closed_with_difference: "warning", pending_manager_approval: "warning", cancelled: "danger" }[value] || "secondary");
const movementColumns = [{ key: "when", label: "Data" }, { key: "type", label: "Movimento" }, { key: "amount", label: "Valor", type: "money", align: "right" }, { key: "balance_after", label: "Saldo após", type: "money", align: "right" }, { key: "status_label", label: "Status" }, { key: "reason", label: "Motivo" }, { key: "destination", label: "Destino/origem" }, { key: "operator_name", label: "Operador" }, { key: "terminal_label", label: "Terminal" }, { key: "authorization_label", label: "Autorização" }, { key: "order_label", label: "Pedido" }];
const saleColumns = [{ key: "when", label: "Data" }, { key: "order_label", label: "Pedido" }, { key: "payment_method_name", label: "Forma" }, { key: "subtype", label: "Tipo" }, { key: "amount", label: "Valor", type: "money", align: "right" }, { key: "change_amount", label: "Troco", type: "money", align: "right" }];
const orderColumns = [{ key: "order_label", label: "Pedido" }, { key: "reference", label: "Referência" }, { key: "type_label", label: "Tipo" }, { key: "opened", label: "Abertura" }, { key: "closed", label: "Fechamento" }, { key: "operator_name", label: "Operador" }, { key: "closed_by_name", label: "Fechado por" }, { key: "status_label", label: "Status" }, { key: "payment_status_label", label: "Pagamento" }, { key: "subtotal", label: "Subtotal", type: "money", align: "right" }, { key: "service_fee", label: "Serviço", type: "money", align: "right" }, { key: "discount", label: "Desconto", type: "money", align: "right" }, { key: "delivery_fee", label: "Entrega", type: "money", align: "right" }, { key: "total", label: "Total", type: "money", align: "right" }, { key: "details", label: "Observações/falhas" }];
const itemColumns = [{ key: "order_label", label: "Pedido" }, { key: "reference", label: "Referência" }, { key: "product_name", label: "Produto" }, { key: "quantity", label: "Qtd.", type: "decimal", align: "right" }, { key: "unit_price", label: "Unitário", type: "money", align: "right" }, { key: "total_price", label: "Total", type: "money", align: "right" }, { key: "status_label", label: "Status" }, { key: "production_sector", label: "Setor" }, { key: "details", label: "Observações/falhas" }];
const movementRows = computed(() => (session.value?.movements || []).map((row) => ({ ...row, when: dateTime(row.created_at), type: TYPES[row.movement_type] || row.movement_type, status_label: statusLabel(row.status), authorization_label: AUTH[row.authorization] || row.authorization, order_label: row.order_sequence ? `#${row.order_sequence}` : "—" })));
const saleRows = computed(() => (session.value?.sales || []).map((row) => ({ ...row, when: dateTime(row.paid_at), order_label: `#${row.order_sequence}`, subtype: row.card_subtype || row.method_type })));
const variationText = (value) => value && Object.keys(value).length ? `Variações: ${JSON.stringify(value)}` : "";
const orderRows = computed(() => (statement.value.orders || []).map((order) => ({ ...order, order_label: `#${order.sequence}`, type_label: ORDER_TYPE[order.order_type] || order.order_type, opened: dateTime(order.opened_at), closed: dateTime(order.closed_at), status_label: ORDER_STATUS[order.status] || order.status, payment_status_label: PAYMENT_STATUS[order.payment_status] || order.payment_status, details: [order.notes, order.cancel_reason].filter(Boolean).join(" · ") || "—" })));
const itemRows = computed(() => (statement.value.orders || []).flatMap((order) => (order.items || []).map((item) => ({ ...item, order_label: `#${order.sequence}`, reference: order.reference, status_label: ITEM_STATUS[item.status] || item.status, details: [variationText(item.variations), ...(item.addons || []).map((addon) => `+ ${addon.quantity}x ${addon.name}`), item.customer_note, item.void_reason].filter(Boolean).join(" · ") || "—" }))));
const occurrences = computed(() => [...movementRows.value.filter((row) => row.status !== "approved").map((row) => ({ key: `m-${row.id}`, kind: row.status_label, tone: row.status === "pending" ? "warning" : "danger", text: `${row.type}: ${money(row.amount)} — ${row.reason || 'sem motivo'}` })), ...orderRows.value.filter((row) => row.status === "cancelled").map((row) => ({ key: `o-${row.id}`, kind: "Pedido cancelado", tone: "danger", text: `${row.order_label} · ${row.reference} — ${row.cancel_reason || 'sem motivo'}` })), ...itemRows.value.filter((row) => ["cancelled", "comped"].includes(row.status)).map((row) => ({ key: `i-${row.id}`, kind: row.status === "comped" ? "Cortesia" : "Cancelado", tone: "danger", text: `Pedido ${row.order_label}: ${row.product_name} — ${row.details}` }))]);

function openMovement(row) { selectedMovement.value = row; movementDialog.value = true; }
function printStatement() { printCashSessionStatement(statement.value); }
async function load() { loading.value = true; try { statement.value = (await api.get(`/cash-register/${route.params.id}/statement/`)).data; } catch (cause) { error.value = normalizeApiError(cause).message; } finally { loading.value = false; } }
onMounted(load);
</script>

<style>
.cash-statement{display:flex;flex-direction:column;gap:20px;max-width:1280px;margin:0 auto}.cash-statement__header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.cash-statement__header>div:first-child{display:flex;flex-direction:column;gap:5px}.cash-statement__header h1,.cash-statement__header p{margin:0}.cash-statement__header small{color:var(--brand);font-weight:700;letter-spacing:.08em}.cash-statement__back{align-self:flex-start;border:0;background:none;color:var(--text-muted);cursor:pointer;padding:0 0 8px}.cash-statement__actions{display:flex;gap:8px}.cash-statement__identity{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;overflow:hidden;border:1px solid var(--border);border-radius:var(--radius-lg);background:var(--border)}.cash-statement__identity>div{display:flex;flex-direction:column;gap:6px;padding:14px;background:var(--surface-card)}.cash-statement__identity small{color:var(--text-muted);font-size:11px;text-transform:uppercase}.cash-statement__identity b{overflow-wrap:anywhere}.cash-statement__issues{display:flex;flex-direction:column;gap:10px;margin:0;padding:0;list-style:none}.cash-statement__issues li{display:flex;align-items:center;gap:10px}.cash-statement__state{padding:40px;text-align:center;color:var(--text-muted)}.cash-statement__state--error{color:var(--danger-text)}
@media(max-width:720px){.cash-statement{gap:14px}.cash-statement__header{flex-direction:column}.cash-statement__actions{width:100%}.cash-statement__actions>*{flex:1}.cash-statement__identity{grid-template-columns:1fr 1fr}}
@media(max-width:460px){.cash-statement__identity{grid-template-columns:1fr}}
@media print{body.cash-session-print .sidebar,body.cash-session-print .topbar,body.cash-session-print .mobile-bottom-nav,body.cash-session-print .screen-only{display:none!important}body.cash-session-print .app-content{padding:0!important;overflow:visible!important}body.cash-session-print .app-main{overflow:visible!important}body.cash-session-print .cash-statement{max-width:none;gap:12px;color:#000}body.cash-session-print .p-paginator{display:none!important}body.cash-session-print .sc-card{break-inside:avoid;box-shadow:none!important}}
</style>
