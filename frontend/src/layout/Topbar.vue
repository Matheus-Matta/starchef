<template>
  <header class="topbar">
    <button class="icon-button topbar__menu-trigger" type="button" aria-label="Menu" @click="$emit('toggle-sidebar')">
      <AppIcon name="panel-left" :size="19" />
    </button>
    <button class="topbar__mobile-back" type="button" aria-label="Voltar" @click="goBack">
      <AppIcon name="arrow-left" :size="19" />
    </button>

    <div class="topbar__title">
      <h1>{{ title }}</h1>
      <span>{{ contextLine }}</span>
    </div>

    <GlobalSearch />

    <div class="topbar__divider" />

    <button class="icon-button" type="button" aria-label="Tema" @click="$emit('toggle-theme')">
      <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
    </button>
    <NotificationBell />

    <div class="topbar__user-wrap">
      <button class="topbar__user" type="button" aria-haspopup="menu" :aria-expanded="profileOpen" @click="profileOpen = !profileOpen">
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
        </div>
        <a
          class="topbar__help"
          href="https://wa.me/5521966621486?text=Ol%C3%A1%2C%20preciso%20de%20ajuda%20com%20o%20StarChef."
          target="_blank"
          rel="noopener noreferrer"
          role="menuitem"
          @click="profileOpen = false"
        >
          <AppIcon name="life-buoy" :size="16" />
          Ajuda pelo WhatsApp
        </a>
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
import { useRouter } from "vue-router";

import AppIcon from "../components/AppIcon.vue";
import GlobalSearch from "../components/GlobalSearch.vue";
import NotificationBell from "../components/NotificationBell.vue";

const props = defineProps({
  title: { type: String, default: "Painel" },
  theme: { type: String, default: "light" },
  user: { type: Object, default: null },
  stats: { type: Object, default: () => ({}) },
  scope: { type: Object, default: null },
});

const emit = defineEmits(["toggle-sidebar", "toggle-theme", "logout"]);
const router = useRouter();
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
const contextLine = computed(() => `${restaurantName.value} - ${today.value}`);
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

function logout() {
  profileOpen.value = false;
  emit("logout");
}

function goBack() {
  if (window.history.length > 1) router.back();
  else router.push({ name: "painel" });
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

.topbar__divider {
  width: 1px;
  height: 28px;
  background: var(--border);
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

.topbar__profile-menu button,
.topbar__help {
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
  text-decoration: none;
}

.topbar__help {
  color: var(--text-body);
}

.topbar__help:hover {
  background: var(--surface-sunken);
}

.topbar__profile-menu button:hover {
  background: var(--danger-subtle);
}

@media (max-width: 980px) {
  .topbar__user-text,
  .topbar__divider {
    display: none;
  }
}

@media (max-width: 760px) {
  /* Libera espaço no mobile: a linha de contexto (restaurante · data) some;
     o título da página já identifica a tela. */
  .topbar__title span {
    display: none;
  }
  .topbar__title h1 {
    font-size: 17px;
  }
}

.topbar__mobile-back {
  display: none;
}

@media (max-width: 900px) {
  .topbar {
    height: 52px;
    padding: 0 14px;
    gap: 8px;
  }

  .topbar__menu-trigger,
  .topbar :deep(.gsearch),
  .topbar__divider,
  .topbar > .icon-button:not(.topbar__menu-trigger) {
    display: none;
  }

  .topbar__title { flex: 1; }
  .topbar__mobile-back {
    width: 36px;
    height: 36px;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 0;
    border-radius: 50%;
    background: var(--surface-sunken);
    color: var(--text-strong);
  }
  .topbar__title h1 { font-size: 15px; }
  .topbar__title span { display: none; }
  .topbar__user-wrap { display: none; }
}

@media (max-width: 640px) {
  .topbar {
    padding-inline: 12px;
  }
}
</style>
