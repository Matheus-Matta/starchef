<template>
  <main class="discrepancy-report">
    <header class="discrepancy-report__header">
      <div>
        <button class="discrepancy-report__back screen-only" type="button" @click="router.back()">← Voltar</button>
        <small>FINANCEIRO</small>
        <h1>Divergências de vendas</h1>
        <p>{{ sessionIds.length }} {{ sessionIds.length === 1 ? 'sessão selecionada' : 'sessões selecionadas' }} · vendas no PDV × valor recebido</p>
      </div>
      <Button class="screen-only" label="Imprimir" icon="pi pi-print" @click="print" />
    </header>

    <div v-if="loading" class="discrepancy-report__state">Carregando relatório...</div>
    <Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
    <template v-else-if="report">
      <section class="discrepancy-report__totals">
        <div><small>Vendas registradas no PDV</small><b>{{ money(report.totals.registered_sales) }}</b></div>
        <div class="is-warn"><small>Divergências</small><b>{{ money(report.totals.discrepancy_total) }}</b></div>
        <div><small>Total recebido</small><b>{{ money(report.totals.received_total) }}</b></div>
        <div><small>Divergências abertas</small><b>{{ report.totals.open_count }}</b></div>
      </section>

      <Card title="Por forma de pagamento" subtitle="O que o PDV registrou e o que entrou sem venda" padding="none">
        <ReportDataTable :rows="methodRows(report.totals)" :columns="methodColumns" />
      </Card>

      <Card v-for="session in report.sessions" :key="session.cash_register" :title="session.cash_station_name || 'Caixa'" :subtitle="sessionSubtitle(session)">
        <div class="discrepancy-report__session">
          <div><small>Vendas no PDV</small><b>{{ money(session.registered_sales) }}</b></div>
          <div class="is-warn"><small>Divergência</small><b>{{ money(session.discrepancy_total) }}</b></div>
          <div><small>Total recebido</small><b>{{ money(session.received_total) }}</b></div>
          <div><small>Diferença da gaveta</small><b>{{ money(session.drawer_difference) }}</b></div>
        </div>
        <ReportDataTable v-if="session.registered_by_method.length || session.discrepancy_by_method.length" :rows="methodRows(session)" :columns="methodColumns" />
        <SalesDiscrepancyList :items="session.discrepancies" :can-decide="canDecide" @changed="load" />
        <div class="discrepancy-report__session-actions screen-only">
          <Button label="Registrar divergência" icon="pi pi-plus" outlined size="small" @click="openRegister(session.cash_register)" />
          <Button label="Ver extrato" icon="pi pi-external-link" text size="small" @click="router.push({ name: 'caixa-sessao-detalhe', params: { id: session.cash_register } })" />
        </div>
      </Card>
    </template>

    <SalesDiscrepancyDialog v-model:visible="registerVisible" :cash-register="registerFor" @saved="load" />
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import Button from "primevue/button";
import Message from "primevue/message";

import SalesDiscrepancyDialog from "../components/cash/SalesDiscrepancyDialog.vue";
import SalesDiscrepancyList from "../components/cash/SalesDiscrepancyList.vue";
import ReportDataTable from "../components/data/ReportDataTable.vue";
import Card from "../components/display/Card.vue";
import { fetchReport } from "../services/cashDiscrepancies";
import { useAuthStore } from "../stores/auth";
import { normalizeApiError } from "../utils/apiError";

const route = useRoute(), router = useRouter(), auth = useAuthStore();
const report = ref(null), loading = ref(true), error = ref("");
const registerVisible = ref(false), registerFor = ref("");
const sessionIds = computed(() => String(route.query.sessoes || "").split(",").map((id) => id.trim()).filter(Boolean));
/** Analisar/regularizar é gesto gerencial; o backend revalida (403). */
const canDecide = computed(() => auth.user?.is_superuser || ["admin", "owner", "manager"].includes(auth.user?.profile_type));
const money = (value) => Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const dateTime = (value) => (value ? new Date(value).toLocaleString("pt-BR") : "—");
const methodColumns = [
  { key: "name", label: "Forma" },
  { key: "registered", label: "Vendas no PDV", type: "money", align: "right" },
  { key: "discrepancy", label: "Divergência", type: "money", align: "right" },
  { key: "received", label: "Recebido", type: "money", align: "right" },
];

/** Junta as duas listas por forma: a mesma forma vira uma linha só. */
function methodRows(source) {
  const rows = new Map();
  const add = (list, field) => (list || []).forEach((method) => {
    const row = rows.get(method.payment_method) || { id: method.payment_method, name: method.name, registered: 0, discrepancy: 0 };
    row[field] = (Math.round(row[field] * 100) + Math.round(Number(method.amount) * 100)) / 100;
    rows.set(method.payment_method, row);
  });
  add(source.registered_by_method, "registered");
  add(source.discrepancy_by_method, "discrepancy");
  return [...rows.values()].map((row) => ({ ...row, received: (Math.round(row.registered * 100) + Math.round(row.discrepancy * 100)) / 100 }));
}

const sessionSubtitle = (session) =>
  `${session.operator_name || 'Operador não identificado'} · ${dateTime(session.opened_at)} → ${dateTime(session.closed_at)}`;

function openRegister(id) {
  registerFor.value = id;
  registerVisible.value = true;
}

async function load() {
  if (!sessionIds.value.length) {
    error.value = "Selecione ao menos uma sessão na página de caixa.";
    loading.value = false;
    return;
  }
  loading.value = !report.value;
  error.value = "";
  try {
    report.value = (await fetchReport(sessionIds.value)).data;
  } catch (cause) {
    error.value = normalizeApiError(cause).message;
  } finally {
    loading.value = false;
  }
}

function print() {
  window.print();
}

onMounted(load);
</script>

<style scoped>
.discrepancy-report{display:flex;flex-direction:column;gap:var(--page-section-gap);max-width:1180px;margin:0 auto}
.discrepancy-report__header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}
.discrepancy-report__header>div{display:flex;flex-direction:column;gap:5px}
.discrepancy-report__header h1,.discrepancy-report__header p{margin:0}
.discrepancy-report__header h1{color:var(--text-strong);font:var(--weight-extra) 24px/1.15 var(--font-sans)}
.discrepancy-report__header small{color:var(--text-brand);font:var(--weight-bold) 11px/1 var(--font-sans);letter-spacing:var(--tracking-caps)}
.discrepancy-report__header p,.discrepancy-report__state{color:var(--text-muted)}
.discrepancy-report__back{align-self:flex-start;border:0;background:none;color:var(--text-brand);cursor:pointer;padding:0}
.discrepancy-report__totals,.discrepancy-report__session{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.discrepancy-report__totals>div,.discrepancy-report__session>div{display:flex;flex-direction:column;gap:4px;padding:14px;background:var(--surface-card);border:1px solid var(--border);border-radius:var(--radius-md)}
.discrepancy-report__totals small,.discrepancy-report__session small{color:var(--text-muted)}
.discrepancy-report__totals b{font-size:20px;color:var(--text-strong)}
.is-warn{border-left:3px solid var(--warning)!important}
.discrepancy-report__session-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}
@media(max-width:720px){.discrepancy-report__header{flex-direction:column}}
@media print{.screen-only{display:none!important}}
</style>
