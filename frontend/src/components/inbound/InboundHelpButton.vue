<template>
  <button class="inbound-help" v-bind="$attrs" type="button" aria-label="Ajuda sobre a consulta SEFAZ" @click="visible = true">
    <i class="pi pi-question-circle" aria-hidden="true" /> Ajuda
  </button>
  <Dialog v-model:visible="visible" modal header="Como funciona a consulta SEFAZ" :style="{ width: 'min(520px, 94vw)' }">
    <div class="inbound-help__content">
      <p>{{ description }}</p>
      <p>Para sincronizar manualmente, escolha a unidade no seletor ao lado de Exportar Selecionadas.</p>
    </div>
  </Dialog>
</template>

<script setup>
import { ref } from "vue";
import Dialog from "primevue/dialog";

defineOptions({ inheritAttrs: false });
defineProps({ description: { type: String, required: true } });
const visible = ref(false);
</script>

<style scoped>
.inbound-help { display: inline-flex; align-items: center; justify-content: center; gap: 7px; height: 38px; padding: 0 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface-card); color: var(--text-body); font: var(--weight-semibold) 13px/1 var(--font-sans); cursor: pointer; transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out); }
.inbound-help:hover { background: var(--surface-hover); border-color: var(--border-strong); }
.inbound-help:active { transform: scale(.98); }
.inbound-help:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
.inbound-help__content { display: grid; gap: 12px; color: var(--text-body); line-height: 1.6; }
.inbound-help__content p { margin: 0; }
</style>
