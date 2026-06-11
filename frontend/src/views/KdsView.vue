<template>
  <div class="kds-grid">
    <div v-for="column in columns" :key="column.key" class="kds-column">
      <div class="kds-column__header" :style="{ background: column.bg, borderColor: column.tone }">
        <span :style="{ color: column.tone }">
          <span :style="{ background: column.tone }" />{{ column.title }}
        </span>
        <strong :style="{ background: column.tone }">{{ column.tickets.length }}</strong>
      </div>

      <article v-for="ticket in column.tickets" :key="ticket.id" class="ticket" :style="{ borderTopColor: column.tone }">
        <div class="ticket__body">
          <div class="ticket__head">
            <div class="ticket__meta">
              <span>{{ ticket.mesa }}</span>
              <small>{{ ticket.id }} · {{ ticket.canal }}</small>
            </div>
            <span class="ticket__time" :style="{ background: column.bg, color: column.tone }">
              <AppIcon name="clock" :size="13" />{{ ticket.t }}
            </span>
          </div>

          <div class="ticket__items">
            <div v-for="(item, index) in ticket.items" :key="`${ticket.id}-${index}`" class="ticket__item">
              <span class="ticket__quantity">{{ item.q }}×</span>
              <span class="ticket__name">
                <strong>{{ item.n }}</strong>
                <small v-if="item.obs">↳ {{ item.obs }}</small>
              </span>
            </div>
          </div>
        </div>

        <button class="ticket__action" type="button" :style="{ background: column.key === 'ready' ? 'var(--success)' : column.tone }">
          <AppIcon :name="actionIcon(column.key)" :size="15" /> {{ actionLabel(column.key) }}
        </button>
      </article>
    </div>
  </div>
</template>

<script setup>
import AppIcon from "../components/AppIcon.vue";

const columns = [
  {
    key: "new",
    title: "Novos",
    tone: "var(--order-new)",
    bg: "var(--order-new-bg)",
    tickets: [
      {
        id: "#1043",
        mesa: "Mesa 08",
        canal: "Salão",
        t: "0:42",
        items: [
          { q: 2, n: "Pizza Margherita", obs: "sem cebola" },
          { q: 1, n: "Refrigerante 600ml" },
        ],
      },
      {
        id: "#1044",
        mesa: "Delivery",
        canal: "iFood",
        t: "1:10",
        items: [
          { q: 1, n: "Hambúrguer Duplo", obs: "ponto ao ponto" },
          { q: 1, n: "Batata frita G" },
          { q: 1, n: "Milk-shake" },
        ],
      },
    ],
  },
  {
    key: "prep",
    title: "Em preparo",
    tone: "var(--order-prep)",
    bg: "var(--order-prep-bg)",
    tickets: [
      {
        id: "#1041",
        mesa: "Mesa 12",
        canal: "Salão",
        t: "4:32",
        items: [
          { q: 1, n: "Risoto de Camarão" },
          { q: 2, n: "Bruschetta" },
          { q: 1, n: "Taça de vinho" },
        ],
      },
      {
        id: "#1039",
        mesa: "Mesa 04",
        canal: "Salão",
        t: "8:05",
        items: [
          { q: 3, n: "Pizza Calabresa" },
          { q: 2, n: "Pizza Portuguesa", obs: "borda recheada" },
        ],
      },
    ],
  },
  {
    key: "ready",
    title: "Prontos",
    tone: "var(--order-ready)",
    bg: "var(--order-ready-bg)",
    tickets: [
      {
        id: "#1038",
        mesa: "Balcão",
        canal: "Balcão",
        t: "0:20",
        items: [
          { q: 1, n: "Espresso Duplo" },
          { q: 1, n: "Pão de queijo" },
        ],
      },
      {
        id: "#1036",
        mesa: "Retirada",
        canal: "Retirada",
        t: "1:48",
        items: [{ q: 2, n: "Lasanha Bolonhesa" }],
      },
    ],
  },
];

function actionLabel(key) {
  return {
    new: "Iniciar preparo",
    prep: "Marcar pronto",
    ready: "Entregar",
  }[key];
}

function actionIcon(key) {
  return {
    new: "play",
    prep: "check",
    ready: "check-check",
  }[key];
}
</script>

<style scoped>
.kds-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kds-column__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 14px;
  border-radius: var(--radius-md);
  border: 1px solid;
}

.kds-column__header span {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: var(--weight-bold) 14px/1 var(--font-sans);
}

.kds-column__header span span {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.kds-column__header strong {
  min-width: 22px;
  height: 22px;
  padding: 0 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  color: #fff;
  font: var(--weight-bold) 12px/1 var(--font-mono);
}

.ticket {
  background: var(--surface-card);
  border: 1px solid var(--border);
  border-top: 3px solid;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.ticket__body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ticket__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.ticket__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ticket__meta span {
  font: var(--weight-bold) 15px/1 var(--font-sans);
  color: var(--text-strong);
}

.ticket__meta small {
  font: var(--weight-bold) 11px/1 var(--font-mono);
  color: var(--text-muted);
}

.ticket__time {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  border-radius: 999px;
  font: var(--weight-bold) 12px/1 var(--font-mono);
}

.ticket__items {
  display: flex;
  flex-direction: column;
  gap: 7px;
  border-top: 1px dashed var(--border);
  padding-top: 11px;
}

.ticket__item {
  display: flex;
  gap: 9px;
  align-items: baseline;
}

.ticket__quantity {
  min-width: 26px;
  height: 22px;
  padding: 0 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  background: var(--surface-sunken);
  color: var(--text-strong);
  font: var(--weight-bold) 12px/1 var(--font-mono);
  flex-shrink: 0;
}

.ticket__name {
  flex: 1;
}

.ticket__name strong {
  font: var(--weight-semibold) 13.5px/1.3 var(--font-sans);
  color: var(--text-body);
}

.ticket__name small {
  display: block;
  font: var(--weight-medium) 11.5px/1.2 var(--font-sans);
  color: var(--warning-text);
  margin-top: 2px;
}

.ticket__action {
  width: 100%;
  height: 40px;
  border: none;
  cursor: pointer;
  border-top: 1px solid var(--border);
  color: #fff;
  font: var(--weight-bold) 13px/1 var(--font-sans);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
}
</style>
