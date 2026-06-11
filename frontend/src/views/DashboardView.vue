<template>
  <div class="dashboard-view">
    <div class="responsive-kpi-grid">
      <StatCard label="Faturamento hoje" value="R$ 16.180" tone="success" delta="12%" delta-dir="up" caption="vs. ontem">
        <template #icon><AppIcon name="dollar-sign" :size="19" /></template>
      </StatCard>
      <StatCard label="Pedidos hoje" value="248" tone="brand" delta="8%" delta-dir="up" caption="18 abertos">
        <template #icon><AppIcon name="receipt-text" :size="19" /></template>
      </StatCard>
      <StatCard label="Ticket médio" value="R$ 65,20" tone="info" delta="3%" delta-dir="up" caption="vs. semana">
        <template #icon><AppIcon name="trending-up" :size="19" /></template>
      </StatCard>
      <StatCard label="Tempo médio cozinha" value="14 min" tone="warning" delta="2 min" delta-dir="down" caption="meta: 15 min">
        <template #icon><AppIcon name="timer" :size="19" /></template>
      </StatCard>
    </div>

    <div class="responsive-two-col">
      <Card title="Faturamento" subtitle="R$ 16.180 hoje · +12% no período">
        <template #actions>
          <Tabs
            v-model="range"
            size="sm"
            :items="[
              { value: 'day', label: 'Dia' },
              { value: 'week', label: 'Semana' },
              { value: 'month', label: 'Mês' },
            ]"
          />
        </template>

        <div class="dashboard-bars">
          <div v-for="bar in bars" :key="bar.d" class="dashboard-bars__item">
            <div class="dashboard-bars__bar" :style="barStyle(bar)">
              <span v-if="bar.v === 100">R$ 3.2k</span>
            </div>
            <span>{{ bar.d }}</span>
          </div>
        </div>
      </Card>

      <Card title="Vendas por canal" subtitle="Hoje">
        <div class="channels">
          <div v-for="channel in channels" :key="channel.label" class="channels__row">
            <div class="channels__meta">
              <span class="channels__label">
                <span :style="{ background: channel.color }" />{{ channel.label }}
              </span>
              <span class="num channels__value">{{ channel.value }}</span>
            </div>
            <div class="channels__track">
              <div :style="{ width: `${channel.pct}%`, background: channel.color }" />
            </div>
          </div>
        </div>
      </Card>
    </div>

    <Card title="Pedidos recentes" subtitle="Atualização em tempo real" padding="none">
      <template #actions>
        <Badge tone="success" dot>Ao vivo</Badge>
      </template>

      <div class="orders-table-wrap">
        <table class="orders-table">
          <thead>
            <tr>
              <th v-for="(header, index) in headers" :key="header || index" :class="{ right: index >= 3 && index <= 4 }">
                {{ header }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in orders" :key="order.id">
              <td class="num strong">{{ order.id }}</td>
              <td class="semibold">{{ order.tipo }}</td>
              <td><span class="muted">{{ order.canal }}</span></td>
              <td class="num right">{{ order.itens }}</td>
              <td class="num right strong">{{ order.total }}</td>
              <td><OrderStatusBadge :status="order.status" size="sm" :pulse="order.status === 'new' || order.status === 'late'" /></td>
              <td class="num" :class="{ danger: order.status === 'late' }">{{ order.t }}</td>
              <td class="right">
                <button class="orders-table__action" type="button" aria-label="Abrir pedido">
                  <AppIcon name="arrow-right" :size="15" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>

<script setup>
import { ref } from "vue";

import AppIcon from "../components/AppIcon.vue";
import StatCard from "../components/data/StatCard.vue";
import Badge from "../components/display/Badge.vue";
import Card from "../components/display/Card.vue";
import OrderStatusBadge from "../components/kitchen/OrderStatusBadge.vue";
import Tabs from "../components/navigation/Tabs.vue";

const range = ref("week");
const headers = ["Pedido", "Tipo", "Canal", "Itens", "Total", "Status", "Tempo", ""];
const bars = [
  { d: "Seg", v: 62 },
  { d: "Ter", v: 48 },
  { d: "Qua", v: 75 },
  { d: "Qui", v: 58 },
  { d: "Sex", v: 96 },
  { d: "Sáb", v: 100 },
  { d: "Dom", v: 71 },
];
const channels = [
  { label: "Salão", value: "R$ 7.420", pct: 46, color: "var(--brand)" },
  { label: "Delivery", value: "R$ 4.180", pct: 26, color: "var(--info)" },
  { label: "Balcão", value: "R$ 2.960", pct: 18, color: "var(--success)" },
  { label: "Retirada", value: "R$ 1.620", pct: 10, color: "var(--warning)" },
];
const orders = [
  { id: "#1042", tipo: "Mesa 12", canal: "Salão", itens: 4, total: "R$ 184,50", status: "prep", t: "4 min" },
  { id: "#1041", tipo: "Delivery", canal: "iFood", itens: 2, total: "R$ 76,90", status: "new", t: "1 min" },
  { id: "#1040", tipo: "Balcão", canal: "Balcão", itens: 1, total: "R$ 28,00", status: "ready", t: "7 min" },
  { id: "#1039", tipo: "Mesa 04", canal: "Salão", itens: 6, total: "R$ 243,00", status: "prep", t: "12 min" },
  { id: "#1038", tipo: "Retirada", canal: "Retirada", itens: 3, total: "R$ 119,70", status: "done", t: "18 min" },
  { id: "#1037", tipo: "Delivery", canal: "WhatsApp", itens: 5, total: "R$ 162,40", status: "late", t: "34 min" },
];

function barStyle(bar) {
  return {
    height: `${bar.v}%`,
    background: bar.v === 100 ? "var(--brand)" : "var(--brand-subtle-2)",
  };
}
</script>

<style scoped>
.dashboard-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.dashboard-bars {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  height: 200px;
  padding-top: 16px;
}

.dashboard-bars__item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  height: 100%;
  justify-content: flex-end;
}

.dashboard-bars__bar {
  width: 100%;
  max-width: 38px;
  border-radius: var(--radius-sm) var(--radius-sm) 3px 3px;
  position: relative;
  transition: height var(--dur-slow) var(--ease-out);
}

.dashboard-bars__bar span {
  position: absolute;
  top: -22px;
  left: 50%;
  transform: translateX(-50%);
  font: var(--weight-bold) 11px/1 var(--font-mono);
  color: var(--text-strong);
  white-space: nowrap;
}

.dashboard-bars__item > span {
  font: var(--weight-semibold) 11px/1 var(--font-sans);
  color: var(--text-muted);
}

.channels {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.channels__row {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.channels__meta {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.channels__label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: var(--weight-semibold) 13px/1 var(--font-sans);
  color: var(--text-body);
}

.channels__label span {
  width: 9px;
  height: 9px;
  border-radius: 3px;
}

.channels__value {
  font: var(--weight-bold) 13px/1 var(--font-mono);
  color: var(--text-strong);
}

.channels__track {
  height: 7px;
  border-radius: 999px;
  background: var(--surface-sunken);
  overflow: hidden;
}

.channels__track div {
  height: 100%;
  border-radius: 999px;
}

.orders-table-wrap {
  overflow-x: auto;
}

.orders-table {
  width: 100%;
  border-collapse: collapse;
}

.orders-table th {
  text-align: left;
  padding: 12px 18px;
  font: var(--weight-bold) 11px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--text-subtle);
  border-bottom: 1px solid var(--border);
  background: var(--surface-sunken);
  white-space: nowrap;
}

.orders-table td {
  padding: 13px 18px;
  white-space: nowrap;
  border-bottom: 1px solid var(--border-subtle);
  font: var(--weight-medium) 13px/1 var(--font-sans);
  color: var(--text-body);
}

.orders-table .right {
  text-align: right;
}

.orders-table .strong {
  font-weight: var(--weight-bold);
  color: var(--text-strong);
}

.orders-table .semibold {
  font-weight: var(--weight-semibold);
}

.orders-table .muted {
  font: var(--weight-medium) 12.5px/1 var(--font-sans);
  color: var(--text-muted);
}

.orders-table .danger {
  color: var(--danger-text);
}

.orders-table__action {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
</style>
