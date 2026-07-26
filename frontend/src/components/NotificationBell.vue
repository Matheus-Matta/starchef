<template>
  <div ref="root" class="nbell">
    <button class="icon-button nbell__trigger" type="button" :aria-label="`Notificações${store.unreadCount ? ` (${store.unreadCount} não lidas)` : ''}`" @click="toggle">
      <AppIcon name="bell" :size="18" />
      <span v-if="store.unreadCount" class="nbell__badge">{{ store.unreadCount > 9 ? "9+" : store.unreadCount }}</span>
    </button>

    <div v-if="open" class="nbell__panel">
      <div class="nbell__head">
        <strong>Notificações</strong>
        <button v-if="store.unreadCount" class="nbell__link" type="button" @click="store.markAllRead()">Marcar todas como lidas</button>
      </div>

      <div class="nbell__list">
        <button
          v-for="n in store.items"
          :key="n.id"
          class="nbell__item"
          :class="{ 'nbell__item--unread': !n.is_read }"
          type="button"
          @click="openItem(n)"
        >
          <span class="nbell__item-icon" :data-level="n.level"><i :class="categoryIcon(n.category)" /></span>
          <span class="nbell__item-text">
            <strong>{{ n.title }}</strong>
            <small v-if="n.body">{{ n.body }}</small>
            <span class="nbell__item-time">{{ timeAgo(n.created_at) }}</span>
          </span>
          <span v-if="!n.is_read" class="nbell__dot" aria-hidden="true" />
        </button>

        <div v-if="!store.items.length && !store.loading" class="nbell__empty">
          <i class="pi pi-bell-slash" />
          <span>Nenhuma notificação</span>
        </div>
        <div v-if="store.loading && !store.items.length" class="nbell__empty"><i class="pi pi-spin pi-spinner" /> Carregando…</div>
      </div>

      <div v-if="store.hasMore" class="nbell__foot">
        <button class="nbell__more" type="button" :disabled="store.loading" @click="store.loadMore()">
          {{ store.loading ? "Carregando…" : "Carregar mais" }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";

import AppIcon from "./AppIcon.vue";
import { useNotificationsStore } from "../stores/notifications";

const router = useRouter();
const store = useNotificationsStore();

const root = ref(null);
const open = ref(false);

function toggle() {
  open.value = !open.value;
  if (open.value && !store.items.length && !store.started) store.init();
}

function openItem(n) {
  store.markRead(n.id);
  open.value = false;
  if (n.url) router.push(n.url).catch(() => {});
}

const CATEGORY_ICON = {
  cash: "pi pi-wallet",
  order: "pi pi-receipt",
  payment: "pi pi-dollar",
  kitchen: "pi pi-shopping-bag",
  stock: "pi pi-box",
  system: "pi pi-bell",
};
function categoryIcon(category) {
  return CATEGORY_ICON[category] || "pi pi-bell";
}

/** "há 3 min", "há 2 h", "há 4 d" — tempo relativo compacto. */
function timeAgo(iso) {
  if (!iso) return "";
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return "agora";
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  if (diff < 604800) return `há ${Math.floor(diff / 86400)} d`;
  return new Date(iso).toLocaleDateString("pt-BR");
}

function onDocClick(event) {
  if (root.value && !root.value.contains(event.target)) open.value = false;
}
onMounted(() => document.addEventListener("click", onDocClick));
onUnmounted(() => document.removeEventListener("click", onDocClick));
</script>

<style scoped>
.nbell { position: relative; }
.nbell__trigger { position: relative; }
.nbell__badge {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: var(--danger);
  color: #fff;
  font: var(--weight-bold) 9.5px/1 var(--font-sans);
  border: 2px solid var(--surface-card);
  box-sizing: content-box;
}

.nbell__panel {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: 40;
  width: min(380px, 92vw);
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.nbell__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
}
.nbell__head strong { color: var(--text-strong); font: var(--weight-extra) 14px/1 var(--font-sans); }
.nbell__link {
  background: none; border: none; padding: 0; cursor: pointer;
  color: var(--text-brand); font: var(--weight-semibold) 12px/1 var(--font-sans);
}

.nbell__list { max-height: min(60vh, 420px); overflow-y: auto; }

.nbell__item {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 14px;
  border: none;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.nbell__item:hover { background: var(--surface-hover); }
.nbell__item--unread { background: color-mix(in srgb, var(--brand) 6%, transparent); }

.nbell__item-icon {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
  color: var(--text-muted);
}
.nbell__item-icon .pi { font-size: 0.85rem; }
.nbell__item-icon[data-level="info"] { background: var(--info-subtle); color: var(--info-text); }
.nbell__item-icon[data-level="success"] { background: var(--success-subtle); color: var(--success-text); }
.nbell__item-icon[data-level="warning"] { background: var(--warning-subtle); color: var(--warning-text); }
.nbell__item-icon[data-level="error"] { background: var(--danger-subtle); color: var(--danger-text); }

.nbell__item-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.nbell__item-text strong { color: var(--text-strong); font: var(--weight-semibold) 13px/1.3 var(--font-sans); }
.nbell__item-text small {
  color: var(--text-muted); font: var(--weight-medium) 12px/1.4 var(--font-sans);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.nbell__item-time { color: var(--text-subtle); font: var(--weight-medium) 11px/1 var(--font-sans); margin-top: 2px; }

.nbell__dot { flex-shrink: 0; width: 8px; height: 8px; margin-top: 6px; border-radius: 50%; background: var(--brand); }

.nbell__empty {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 32px 16px; color: var(--text-muted);
  font: var(--weight-medium) 13px/1.4 var(--font-sans);
}
.nbell__empty i { font-size: 24px; color: var(--text-subtle); }

.nbell__foot { padding: 8px; border-top: 1px solid var(--border-subtle); }
.nbell__more {
  width: 100%; height: 36px; border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-card); color: var(--text-body);
  font: var(--weight-semibold) 12.5px/1 var(--font-sans); cursor: pointer;
}
.nbell__more:hover:not(:disabled) { background: var(--surface-hover); }
.nbell__more:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
