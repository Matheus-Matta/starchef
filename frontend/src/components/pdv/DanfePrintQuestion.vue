<template>
  <div
    v-if="summary"
    class="danfe-question__overlay"
    role="dialog"
    aria-modal="true"
    aria-labelledby="danfe-question-title"
    @click.self="emit('cancel')"
  >
    <div class="danfe-question__modal">
      <h3 id="danfe-question-title">Imprimir a NFC-e?</h3>
      <p>{{ summary }}</p>
      <div class="danfe-question__actions">
        <button type="button" class="danfe-question__btn" @click="emit('cancel')">Cancelar (Esc)</button>
        <button type="button" class="danfe-question__btn danfe-question__btn--primary" @click="emit('print')">
          <i class="pi pi-print" /> Imprimir (Enter)
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, watch } from "vue";

// Feito para teclado: Enter imprime, Esc cancela. Clicar em Cancelar ou fora
// do modal também cancela.
const props = defineProps({
  summary: { type: String, default: "" },
});
const emit = defineEmits(["print", "cancel"]);

function onKey(event) {
  if (event.key === "Enter") {
    event.preventDefault();
    emit("print");
  } else if (event.key === "Escape") {
    event.preventDefault();
    emit("cancel");
  }
}

// O ouvinte vive só enquanto a pergunta está na tela: aberto o tempo todo,
// todo Enter do PDV (busca, teclado de pagamento) cairia aqui.
watch(
  () => props.summary,
  (aberto) => {
    window.removeEventListener("keydown", onKey, true);
    if (aberto) window.addEventListener("keydown", onKey, true);
  },
  { immediate: true },
);
onBeforeUnmount(() => window.removeEventListener("keydown", onKey, true));
</script>

<style scoped>
.danfe-question__overlay {
  position: fixed; inset: 0; z-index: 120;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0, 0, 0, 0.4);
}
.danfe-question__modal {
  width: calc(100% - 32px); max-width: 400px; padding: 24px;
  display: flex; flex-direction: column; gap: 12px;
  border-radius: var(--radius-lg); background: var(--surface-card); box-shadow: var(--shadow-lg);
}
.danfe-question__modal h3 { margin: 0; color: var(--text-body); font: var(--weight-bold) 18px/1.2 var(--font-sans); }
.danfe-question__modal p { margin: 0; color: var(--text-muted); }
.danfe-question__actions { display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.danfe-question__btn {
  display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 16px;
  border: 1px solid var(--border); border-radius: var(--radius-md);
  background: var(--surface-active); color: var(--text-body);
  font: var(--weight-bold) 13px/1 var(--font-sans); cursor: pointer;
}
.danfe-question__btn--primary { border-color: transparent; background: var(--brand); color: #fff; }
</style>
