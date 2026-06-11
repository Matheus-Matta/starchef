<template>
  <aside class="sidebar" :style="{ width: collapsed ? 'var(--sidebar-w-mini)' : 'var(--sidebar-w)' }">
    <div class="sidebar__brand" :style="brandStyle">
      <img :src="logoUrl" width="34" height="34" alt="StarChef" />
      <span v-if="!collapsed" class="sidebar__brand-name">Star<span>Chef</span></span>
    </div>

    <button v-if="!collapsed" class="sidebar__branch" type="button">
      <span class="sidebar__branch-icon">
        <AppIcon name="store" :size="16" />
      </span>
      <span class="sidebar__branch-text">
        <span class="sidebar__branch-title">{{ branch }}</span>
        <span class="sidebar__branch-subtitle">Filial Centro</span>
      </span>
      <AppIcon name="chevrons-up-down" :size="15" />
    </button>

    <nav class="sidebar__nav">
      <div v-for="group in groups" :key="group.label" class="sidebar__group">
        <div v-if="!collapsed" class="sidebar__group-label">{{ group.label }}</div>
        <div class="sidebar__items">
          <button
            v-for="item in group.items"
            :key="item.id"
            type="button"
            class="sidebar__item"
            :class="{ 'sidebar__item--active': active === item.id }"
            :title="item.label"
            :style="itemStyle(item.id)"
            @click="$emit('navigate', item.id)"
          >
            <span v-if="active === item.id" class="sidebar__active-bar" />
            <AppIcon :name="item.icon" :size="18" />
            <span v-if="!collapsed" class="sidebar__item-label">{{ item.label }}</span>
            <span v-if="!collapsed && item.badge" class="sidebar__badge" :style="badgeStyle(item)">
              {{ item.badge }}
            </span>
          </button>
        </div>
      </div>
    </nav>

    <div v-if="!collapsed" class="sidebar__footer">
      <div class="sidebar__help">
        <AppIcon name="life-buoy" :size="17" />
        <span>Suporte & ajuda</span>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed } from "vue";

import logoUrl from "../assets/logo-mark.svg";
import AppIcon from "../components/AppIcon.vue";

const props = defineProps({
  active: { type: String, default: "painel" },
  collapsed: { type: Boolean, default: false },
  branch: { type: String, default: "Cantina da Ana" },
});

defineEmits(["navigate"]);

const groups = [
  {
    label: "Principal",
    items: [
      { id: "painel", label: "Painel", icon: "layout-dashboard" },
      { id: "pedidos", label: "Pedidos", icon: "receipt-text", badge: "18" },
      { id: "kds", label: "KDS Cozinha", icon: "soup", badge: "6", badgeTone: "warning" },
    ],
  },
  {
    label: "Operação",
    items: [
      { id: "mesas", label: "Mesas & Comandas", icon: "armchair" },
      { id: "cardapio", label: "Cardápio", icon: "book-open" },
      { id: "caixa", label: "Caixa", icon: "wallet" },
      { id: "clientes", label: "Clientes", icon: "users" },
    ],
  },
  {
    label: "Gestão",
    items: [
      { id: "estoque", label: "Estoque", icon: "package" },
      { id: "relatorios", label: "Relatórios", icon: "bar-chart-3" },
      { id: "restaurantes", label: "Restaurantes", icon: "store" },
      { id: "usuarios", label: "Usuários", icon: "user-cog" },
    ],
  },
];

const brandStyle = computed(() => ({
  padding: props.collapsed ? "0" : "0 20px",
  justifyContent: props.collapsed ? "center" : "flex-start",
}));

function itemStyle(id) {
  const on = props.active === id;
  return {
    padding: props.collapsed ? "0" : "0 10px",
    justifyContent: props.collapsed ? "center" : "flex-start",
    background: on ? "var(--nav-item-active)" : "transparent",
    color: on ? "var(--text-brand)" : "var(--text-body)",
    font: `${on ? "var(--weight-bold)" : "var(--weight-medium)"} 13.5px/1 var(--font-sans)`,
  };
}

function badgeStyle(item) {
  const on = props.active === item.id;
  return {
    background: item.badgeTone === "warning" ? "var(--warning-subtle)" : on ? "var(--brand)" : "var(--surface-active)",
    color: item.badgeTone === "warning" ? "var(--warning-text)" : on ? "#fff" : "var(--text-muted)",
  };
}
</script>

<style scoped>
.sidebar {
  flex-shrink: 0;
  background: var(--surface-nav);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  height: 100vh;
  transition: width var(--dur-base) var(--ease-out);
  overflow: hidden;
}

.sidebar__brand {
  height: var(--topbar-h);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 11px;
  border-bottom: 1px solid var(--border-subtle);
}

.sidebar__brand-name {
  font: var(--weight-extra) 20px/1 var(--font-sans);
  letter-spacing: -0.02em;
  color: var(--text-strong);
}

.sidebar__brand-name span {
  color: var(--brand);
}

.sidebar__branch {
  margin: 14px 14px 6px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: left;
  color: var(--text-body);
}

.sidebar__branch-icon {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  background: var(--brand-subtle);
  color: var(--brand);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sidebar__branch-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.sidebar__branch-title {
  font: var(--weight-bold) 13px/1.2 var(--font-sans);
  color: var(--text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sidebar__branch-subtitle {
  font: var(--weight-medium) 11px/1 var(--font-sans);
  color: var(--text-muted);
}

.sidebar__nav {
  flex: 1;
  overflow-y: auto;
  padding: 8px 14px 14px;
}

.sidebar__group {
  margin-top: 14px;
}

.sidebar__group-label {
  font: var(--weight-bold) 10px/1 var(--font-sans);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--text-subtle);
  padding: 6px 10px 10px;
}

.sidebar__items {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.sidebar__item {
  display: flex;
  align-items: center;
  gap: 11px;
  height: 40px;
  width: 100%;
  border: none;
  cursor: pointer;
  border-radius: var(--radius-md);
  position: relative;
}

.sidebar__item:not(.sidebar__item--active):hover {
  background: var(--nav-item-hover) !important;
}

.sidebar__active-bar {
  position: absolute;
  left: -14px;
  top: 9px;
  bottom: 9px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--brand);
}

.sidebar__item-label {
  flex: 1;
  text-align: left;
}

.sidebar__badge {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-pill);
  font: var(--weight-bold) 11px/1 var(--font-mono);
}

.sidebar__footer {
  padding: 14px;
  border-top: 1px solid var(--border-subtle);
}

.sidebar__help {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
  font: var(--weight-semibold) 12.5px/1 var(--font-sans);
  color: var(--text-body);
}

@media (max-width: 760px) {
  .sidebar {
    display: none;
  }
}
</style>
