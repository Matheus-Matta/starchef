<template>
  <div class="commands-report report-panel">
    <h3 class="commands-report__titulo">Agora no salão</h3>
    <div class="responsive-kpi-grid">
      <StatCard
        label="Em uso agora" :value="inteiro(agora.in_use)" tone="brand"
        :caption="`de ${inteiro(agora.registered)} cadastradas · ${inteiro(agora.free)} livres`"
      >
        <template #icon><AppIcon name="clipboard-list" :size="19" /></template>
      </StatCard>
      <StatCard
        label="A receber nas comandas" :value="dinheiro(agora.in_use_total)" tone="info"
        :caption="`${inteiro(agora.in_use_items)} itens lançados e não pagos`"
      >
        <template #icon><AppIcon name="wallet" :size="19" /></template>
      </StatCard>
      <StatCard
        label="Presas em conta aberta" :value="inteiro(agora.in_open_bill)" tone="warning"
        caption="Levadas a uma conta que ninguém pagou"
      >
        <template #icon><AppIcon name="warning" :size="19" /></template>
      </StatCard>
      <StatCard label="Livres" :value="inteiro(agora.free)" tone="success" caption="Prontas para o próximo cliente">
        <template #icon><AppIcon name="check-circle" :size="19" /></template>
      </StatCard>
    </div>

    <h3 class="commands-report__titulo">No período</h3>
    <div class="responsive-kpi-grid">
      <StatCard
        label="Comandas pagas" :value="inteiro(periodo.paid)" tone="success"
        :caption="`${dinheiro(periodo.paid_total)} recebidos`"
      >
        <template #icon><AppIcon name="receipt-text" :size="19" /></template>
      </StatCard>
      <StatCard
        label="Ticket médio por comanda" :value="dinheiro(periodo.average_ticket)" tone="brand"
        :caption="`${decimal(periodo.average_items_per_paid)} itens por comanda paga`"
      >
        <template #icon><AppIcon name="ticket" :size="19" /></template>
      </StatCard>
      <StatCard
        label="Comandas usadas" :value="inteiro(periodo.used)" tone="info"
        :caption="`${inteiro(periodo.launched_items)} itens lançados · ${dinheiro(periodo.launched_total)}`"
      >
        <template #icon><AppIcon name="users" :size="19" /></template>
      </StatCard>
      <StatCard
        label="Tempo médio aberta" :value="duracao(periodo.average_stay_minutes)" tone="neutral"
        caption="Do primeiro lançamento ao pagamento"
      >
        <template #icon><AppIcon name="timer" :size="19" /></template>
      </StatCard>
      <StatCard
        label="Consumo perdido" :value="dinheiro(periodo.lost_total)" tone="danger"
        :caption="`${inteiro(periodo.lost_items)} itens de contas canceladas`"
      >
        <template #icon><AppIcon name="minus" :size="19" /></template>
      </StatCard>
    </div>

    <div class="responsive-one-col">
      <Card title="Comandas em uso agora" subtitle="A aberta há mais tempo primeiro" padding="none">
        <ReportDataTable :rows="linhasEmUso" :columns="colunasEmUso" />
      </Card>
      <Card title="Por comanda no período" subtitle="Cada número: quantas vezes foi paga e quanto vendeu" padding="none">
        <ReportDataTable :rows="linhasPorComanda" :columns="colunasPorComanda" />
      </Card>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

import AppIcon from "../AppIcon.vue";
import Card from "../display/Card.vue";
import StatCard from "../data/StatCard.vue";
import ReportDataTable from "../data/ReportDataTable.vue";
import { duracao } from "../../utils/duracao";

const props = defineProps({
  report: { type: Object, required: true },
});

// O relatório chega vazio enquanto carrega: os cartões mostram zero, não erro.
const agora = computed(() => props.report.now || {});
const periodo = computed(() => props.report.period || {});

const inteiro = (valor) => Number(valor || 0).toLocaleString("pt-BR");
const decimal = (valor) => Number(valor || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
const dinheiro = (valor) => Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const hora = (valor) => (valor ? new Date(valor).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");
const minutosDesde = (valor) => (valor ? (Date.now() - new Date(valor).getTime()) / 60000 : null);

const colunasEmUso = [
  { key: "number", label: "Comanda" },
  { key: "customer", label: "Cliente" },
  { key: "table", label: "Mesa" },
  { key: "items", label: "Itens", align: "right" },
  { key: "total", label: "A receber", align: "right", type: "money" },
  // Minutos, e não o texto: a coluna ordena pelo tempo de verdade.
  { key: "aberta_ha", label: "Aberta há", align: "right", type: "duration" },
  { key: "last_launch_label", label: "Último lançamento" },
  { key: "situacao", label: "Situação" },
];

const linhasEmUso = computed(() =>
  (props.report.open_commands || []).map((linha) => ({
    ...linha,
    customer: linha.customer_name || "—",
    table: linha.table || "—",
    aberta_ha: minutosDesde(linha.open_since),
    last_launch_label: hora(linha.last_launch),
    situacao: linha.in_open_bill ? "Em conta aberta" : "Anotando",
  })),
);

const colunasPorComanda = [
  { key: "number", label: "Comanda" },
  { key: "uses", label: "Vezes paga", align: "right" },
  { key: "items", label: "Itens", align: "right" },
  { key: "total", label: "Total", align: "right", type: "money" },
  { key: "last_use_label", label: "Último pagamento" },
];

const linhasPorComanda = computed(() =>
  (props.report.by_command || []).map((linha) => ({ ...linha, last_use_label: hora(linha.last_use) })),
);
</script>

<style scoped>
.commands-report__titulo {
  margin: 4px 0 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-muted);
}
</style>
