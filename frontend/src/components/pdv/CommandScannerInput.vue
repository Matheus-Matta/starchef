<template>
  <form class="scanner" @submit.prevent="submit">
    <label class="scanner__label" :for="inputId">Passe o cartão ou digite o número</label>
    <div class="scanner__row">
      <input
        :id="inputId"
        ref="campo"
        v-model="valor"
        class="scanner__input"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        :disabled="disabled"
        placeholder="Código de barras, número ou QR da comanda"
      />
      <button class="scanner__button" type="submit" :disabled="disabled || !valor.trim()">
        Incluir
      </button>
    </div>
    <p v-if="hint" class="scanner__hint">{{ hint }}</p>
  </form>
</template>

<script setup>
/**
 * A porta pela qual a comanda entra na conta agrupada.
 *
 * O leitor de código de barras é um teclado: ele digita o código e manda um
 * Enter. Por isso o campo precisa de DUAS coisas que um input comum não tem:
 *
 * 1. **Foco que volta sozinho.** Depois de cada leitura o campo se limpa e
 *    recupera o foco. Sem isso, a segunda comanda da mesa é digitada em lugar
 *    nenhum e o operador só descobre quando olha a tela — que é justamente o
 *    que ele não faz enquanto passa os cartões.
 * 2. **Enter que não recarrega nada.** O `submit` do formulário é interceptado;
 *    o Enter do leitor vira "incluir esta comanda".
 */
import { nextTick, onMounted, ref } from "vue";

defineProps({
  disabled: { type: Boolean, default: false },
  hint: { type: String, default: "" },
});

const emit = defineEmits(["scan"]);

const inputId = `scanner-${Math.random().toString(16).slice(2)}`;
const valor = ref("");
const campo = ref(null);

function focar() {
  nextTick(() => campo.value?.focus());
}

onMounted(focar);

function submit() {
  const lido = valor.value.trim();
  if (!lido) return;
  valor.value = "";
  focar();
  emit("scan", lido);
}

defineExpose({ focus: focar });
</script>

<style scoped>
.scanner {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.scanner__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-color-secondary, #6b7280);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.scanner__row {
  display: flex;
  gap: 8px;
}

.scanner__input {
  flex: 1;
  min-width: 0;
  /* Alto e com fonte grande: o cartão é passado sem olhar, e a conferência
     visual do que entrou acontece de longe, com o cliente do outro lado. */
  height: 48px;
  padding: 0 12px;
  font-size: 18px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 8px;
  background: var(--surface-card, #fff);
  color: inherit;
}

.scanner__input:focus {
  outline: 2px solid var(--primary-color, #2563eb);
  outline-offset: 1px;
}

.scanner__button {
  height: 48px;
  padding: 0 20px;
  border: 0;
  border-radius: 8px;
  background: var(--primary-color, #2563eb);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}

.scanner__button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.scanner__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-color-secondary, #6b7280);
}
</style>
