<template>
  <header class="topbar">
    <button class="icon-button" type="button" aria-label="Menu" @click="$emit('toggle-sidebar')">
      <AppIcon name="panel-left" :size="19" />
    </button>

    <div class="topbar__title">
      <h1>{{ title }}</h1>
      <span>{{ today }}</span>
    </div>

    <div class="topbar__search">
      <AppIcon name="search" :size="17" />
      <input class="plain-input" placeholder="Buscar pedido, mesa, cliente..." />
      <kbd>Ctrl K</kbd>
    </div>

    <button class="topbar__primary" type="button" @click="$emit('new-order')">
      <AppIcon name="plus" :size="17" /> Novo pedido
    </button>

    <div class="topbar__divider" />

    <button class="icon-button" type="button" aria-label="Tema" @click="$emit('toggle-theme')">
      <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
    </button>
    <button class="icon-button topbar__notification" type="button" aria-label="Notificações">
      <AppIcon name="bell" :size="18" />
      <span />
    </button>

    <button class="topbar__user" type="button" title="Sair" @click="$emit('logout')">
      <Avatar :name="displayName" size="sm" status="online" />
      <span class="topbar__user-text">
        <span>{{ displayName }}</span>
        <small>{{ roleLabel }}</small>
      </span>
      <AppIcon name="chevron-down" :size="15" />
    </button>
  </header>
</template>

<script setup>
import { computed } from "vue";

import AppIcon from "../components/AppIcon.vue";
import Avatar from "../components/display/Avatar.vue";

const props = defineProps({
  title: { type: String, default: "Painel" },
  theme: { type: String, default: "light" },
  user: { type: Object, default: null },
});

defineEmits(["toggle-sidebar", "toggle-theme", "new-order", "logout"]);

const today = computed(() =>
  new Date().toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
  }),
);

const displayName = computed(() => props.user?.name || props.user?.username || "Usuário");
const roleLabel = computed(() => {
  const labels = {
    admin: "Administrador",
    owner: "Proprietário",
    manager: "Gerente",
    waiter: "Garçom",
    kitchen: "Cozinha",
    cashier: "Caixa",
    driver: "Entregador",
  };
  return labels[props.user?.profile_type] || (props.user?.is_superuser ? "Superadmin" : "Operador");
});
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
}

.topbar__title {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.topbar__title h1 {
  font: var(--weight-bold) 19px/1 var(--font-sans);
  color: var(--text-strong);
  letter-spacing: -0.01em;
}

.topbar__title span {
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
