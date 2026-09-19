<template>
  <header class="pdv-bar">
    <div class="pdv-bar__identity">
      <strong class="pdv-bar__cash">{{ cashName }}</strong>
      <span class="pdv-bar__operator">{{ operatorName }} · {{ shiftLabel }}</span>
    </div>

    <div class="pdv-bar__status">
      <span class="pdv-bar__chip" :class="cashOpen ? 'is-good' : 'is-bad'">
        <i :class="cashOpen ? 'pi pi-lock-open' : 'pi pi-lock'" />
        {{ cashOpen ? "Caixa aberto" : "Caixa fechado" }}
      </span>

      <span class="pdv-bar__chip" :class="online ? 'is-good' : 'is-bad'">
        <i :class="online ? 'pi pi-wifi' : 'pi pi-times-circle'" />
        {{ online ? "Conectado" : "Sem conexão" }}
      </span>

      <button class="pdv-bar__icon" type="button" :title="themeTitle" @click="$emit('toggle-theme')">
        <i :class="theme === 'dark' ? 'pi pi-sun' : 'pi pi-moon'" />
      </button>
    </div>
  </header>
</template>

<script setup>
/**
 * Barra de estado do PDV, espelhando `pdv_operational_chrome.dart`.
 *
 * Mostra só o que a web SABE. O desktop exibe impressora, fila de impressão e
 * sincronização pendente porque tem o agente local para responder; aqui um
 * indicador desses teria de adivinhar, e indicador que adivinha é pior que
 * indicador ausente — o operador passa a confiar nele.
 */
import { computed } from "vue";

const props = defineProps({
  cashName: { type: String, default: "StarChef PDV" },
  operatorName: { type: String, default: "" },
  shiftLabel: { type: String, default: "" },
  cashOpen: { type: Boolean, default: false },
  online: { type: Boolean, default: true },
  theme: { type: String, default: "light" },
});

defineEmits(["toggle-theme"]);

const themeTitle = computed(() => (props.theme === "dark" ? "Tema claro" : "Tema escuro"));
</script>

<style scoped>
.pdv-bar {
  /* 52px é a altura da barra no desktop. Mantida igual de propósito: quem
     alterna entre os dois durante o turno não deve sentir a troca. */
  height: 52px;
  flex: 0 0 52px;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 14px;
  background: var(--surface-card, #ffffff);
  border-bottom: 1px solid var(--surface-border, #e5e7eb);
}

.pdv-bar__identity {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.pdv-bar__cash {
  font-size: 15px;
  font-weight: 800;
  line-height: 1.1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pdv-bar__operator {
  font-size: 12px;
  color: var(--text-color-secondary, #6b7280);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pdv-bar__status {
  display: flex;
  align-items: center;
  gap: 10px;
}

.pdv-bar__chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

/* Verde e vermelho escuros: o chip fica sobre fundo claro e sobre fundo
   escuro, e o tom claro some num deles. */
.is-good {
  color: #166534;
}
.is-bad {
  color: #b91c1c;
}

.pdv-bar__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-color-secondary, #6b7280);
  cursor: pointer;
}

.pdv-bar__icon:hover {
  background: var(--surface-hover, #f3f4f6);
}

@media (max-width: 720px) {
  /* Em tela estreita o rótulo some e fica o ícone: o estado continua legível
     e a identidade do caixa não é espremida a ponto de sumir. */
  .pdv-bar__chip span,
  .pdv-bar__chip {
    font-size: 0;
  }
  .pdv-bar__chip i {
    font-size: 16px;
  }
}
</style>
