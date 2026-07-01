<template>
  <header class="topbar">
    <button class="icon-button" type="button" aria-label="Menu" @click="$emit('toggle-sidebar')">
      <AppIcon name="panel-left" :size="19" />
    </button>

    <div class="topbar__title">
      <h1>{{ title }}</h1>
      <span>{{ contextLine }}</span>
    </div>

    <div class="topbar__search">
      <AppIcon name="search" :size="17" />
      <input class="plain-input" placeholder="Buscar pedido, mesa, cliente..." />
      <kbd>Ctrl K</kbd>
    </div>

    <button v-if="canCreateOrder" class="topbar__primary" type="button" @click="$emit('new-order')">
      <AppIcon name="plus" :size="17" /> Novo pedido
    </button>

    <div class="topbar__divider" />

    <button class="icon-button" type="button" aria-label="Tema" @click="$emit('toggle-theme')">
      <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
    </button>
    <button class="icon-button topbar__notification" type="button" :aria-label="notificationLabel">
      <AppIcon name="bell" :size="18" />
      <span v-if="hasOpenWork" />
    </button>

    <div class="topbar__user-wrap">
      <button class="topbar__user" type="button" aria-haspopup="menu" :aria-expanded="profileOpen" @click="profileOpen = !profileOpen">
        <span class="topbar-avatar-wrap">
          <Avatar :label="avatarInitials(displayName)" size="large" />
          <span class="topbar-avatar-dot" />
        </span>
        <span class="topbar__user-text">
          <span>{{ displayName }}</span>
          <small>{{ roleLabel }}</small>
        </span>
        <AppIcon name="chevron-down" :size="15" />
      </button>

      <div v-if="profileOpen" class="topbar__profile-menu" role="menu">
        <div class="topbar__profile-head">
          <strong>{{ displayName }}</strong>
          <span>{{ props.user?.email || props.user?.username }}</span>
        </div>
        <div class="topbar__profile-scope">
          <span>{{ restaurantName }}</span>
          <small>{{ branchName }}</small>
        </div>
        <button type="button" role="menuitem" @click="logout">
          <AppIcon name="log-out" :size="16" />
          Sair
        </button>
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed, ref } from "vue";

import Avatar from "primevue/avatar";

import AppIcon from "../components/AppIcon.vue";

const props = defineProps({
  title: { type: String, default: "Painel" },
  theme: { type: String, default: "light" },
  user: { type: Object, default: null },
  stats: { type: Object, default: () => ({}) },
  scope: { type: Object, default: null },
});

const emit = defineEmits(["toggle-sidebar", "toggle-theme", "new-order", "logout"]);
const profileOpen = ref(false);

const today = computed(() =>
  new Date().toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  }),
);

const displayName = computed(() => props.user?.name || props.user?.username || "Usuario");
const restaurantName = computed(() => props.scope?.restaurantName || props.user?.restaurant_name || props.user?.account_name || "Restaurante");
const branchName = computed(() => props.scope?.branchName || props.user?.branch_name || "Todas as filiais");
const contextLine = computed(() => `${restaurantName.value} - ${branchName.value} - ${today.value}`);
const hasOpenWork = computed(() => Number(props.stats.ordersOpen || 0) > 0 || Number(props.stats.kitchenOpen || 0) > 0);
const canCreateOrder = computed(
  () => props.user?.is_superuser || ["admin", "owner", "manager", "waiter", "cashier"].includes(props.user?.profile_type),
);
const notificationLabel = computed(() => {
  if (!hasOpenWork.value) return "Sem alertas operacionais";
  return `${props.stats.ordersOpen || 0} pedidos abertos, ${props.stats.kitchenOpen || 0} itens na cozinha`;
});
const roleLabel = computed(() => {
  const labels = {
    admin: "Administrador",
    owner: "Proprietario",
    manager: "Gerente",
    waiter: "Garcom",
    kitchen: "Cozinha",
    cashier: "Caixa",
    driver: "Entregador",
  };
  return labels[props.user?.profile_type] || (props.user?.is_superuser ? "Superadmin" : "Operador");
});

function avatarInitials(name) {
  return (name || "?")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

function logout() {
  profileOpen.value = false;
  emit("logout");
}
</script>

<style scoped>
.topbar {
  height: var(--topbar-h);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 22px;
  background: var(--surface-card);
  border-bottom: 1px solid var(--border);
  position: relative;
  z-index: 30;
}

.topbar__title {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.topbar__title h1 {
  font: var(--weight-bold) 19px/1 var(--font-sans);
  color: var(--text-strong);
}

.topbar__title span {
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: var(--weight-medium) 12px/1 var(--font-sans);
  color: var(--text-muted);
}

.topbar__search {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 9px;
  height: 40px;
  width: 280px;
  padding: 0 12px;
  background: var(--surface-sunken);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-subtle);
}

.topbar__search kbd {
  font: var(--weight-semibold) 10px/1 var(--font-mono);
  color: var(--text-subtle);
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 5px;
}

.topbar__primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 16px;
  background: var(--brand);
  color: var(--on-brand);
  border: none;
  cursor: pointer;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-brand);
  font: var(--weight-bold) 13.5px/1 var(--font-sans);
  white-space: nowrap;
}

.topbar__divider {
  width: 1px;
  height: 28px;
  background: var(--border);
}

.topbar__notification {
  position: relative;
}

.topbar__notification span {
  position: absolute;
  top: 7px;
  right: 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--brand);
  border: 2px solid var(--surface-card);
}

.topbar__user {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 42px;
  padding: 0 6px;
  background: transparent;
  border: none;
  cursor: pointer;
  border-radius: var(--radius-md);
  color: var(--text-body);
}

.topbar-avatar-wrap {
  position: relative;
  display: inline-flex;
}

.topbar-avatar-dot {
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--success);
  border: 2px solid var(--surface-card);
}

.topbar__user-wrap {
  position: relative;
}

.topbar__user-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  text-align: left;
}

.topbar__user-text span {
  font: var(--weight-bold) 13px/1 var(--font-sans);
  color: var(--text-strong);
}

.topbar__user-text small {
  font: var(--weight-medium) 11px/1 var(--font-sans);
  color: var(--text-muted);
}

.topbar__profile-menu {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: 20;
  width: 260px;
  padding: 8px;
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
}

.topbar__profile-head,
.topbar__profile-scope {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 9px 10px;
}

.topbar__profile-head {
  border-bottom: 1px solid var(--border-subtle);
}

.topbar__profile-head strong,
.topbar__profile-scope span {
  font: var(--weight-bold) 13px/1.2 var(--font-sans);
  color: var(--text-strong);
}

.topbar__profile-head span,
.topbar__profile-scope small {
  font: var(--weight-medium) 12px/1.2 var(--font-sans);
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
}

.topbar__profile-menu button {
  width: 100%;
  height: 38px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 10px;
  margin-top: 4px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--danger-text);
  cursor: pointer;
  font: var(--weight-bold) 13px/1 var(--font-sans);
  text-align: left;
}

.topbar__profile-menu button:hover {
  background: var(--danger-subtle);
}

@media (max-width: 980px) {
  .topbar__search,
  .topbar__user-text,
  .topbar__divider {
    display: none;
  }
}

@media (max-width: 640px) {
  .topbar {
    padding: 0 12px;
    gap: 10px;
  }

  .topbar__primary {
    display: none;
  }
}
</style>
