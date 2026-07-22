<template>
  <Message v-if="hasErrors" severity="error" :closable="false" class="appsummary">
    <div class="appsummary__body">
      <strong v-if="message" class="appsummary__title">{{ message }}</strong>
      <ul v-if="items.length" class="appsummary__list">
        <li v-for="item in items" :key="item.key">
          <span v-if="item.label" class="appsummary__field">{{ item.label }}:</span>
          {{ item.message }}
        </li>
      </ul>
    </div>
  </Message>
</template>

<script setup>
/**
 * Resumo geral de erros do formulário (Sprint 0 · STC-005).
 * Combina a mensagem geral (`non_field_errors`/`detail`) com os erros por campo,
 * exibindo-os em um único bloco — usado quando o erro não está associado a um
 * campo visível ou como reforço no topo/rodapé do formulário.
 *
 * Alinha-se ao contrato de `useResourceForm`: `message` = saveError,
 * `errors` = fieldErrors ({ campo: mensagem }).
 */
import { computed } from "vue";
import Message from "primevue/message";

const props = defineProps({
  /** Mensagem geral (string) — ex.: saveError. */
  message: { type: String, default: "" },
  /** Erros por campo: { nome: mensagem }. */
  errors: { type: Object, default: () => ({}) },
  /** Rótulos amigáveis por campo: { nome: "Rótulo" }. */
  fieldLabels: { type: Object, default: () => ({}) },
  /** Se false, mostra apenas a mensagem geral (não lista os campos). */
  listFields: { type: Boolean, default: true },
});

const items = computed(() => {
  if (!props.listFields) return [];
  return Object.entries(props.errors || {}).map(([key, msg]) => ({
    key,
    label: props.fieldLabels[key] || "",
    message: Array.isArray(msg) ? msg.join(" ") : String(msg),
  }));
});

const hasErrors = computed(() => Boolean(props.message) || items.value.length > 0);
</script>

<style scoped>
.appsummary { margin: 0; }
.appsummary__body { display: flex; flex-direction: column; gap: 6px; text-align: left; }
.appsummary__title { font: var(--weight-bold) 13px/1.4 var(--font-sans); }
.appsummary__list { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 3px; }
.appsummary__list li { font: var(--weight-medium) 12.5px/1.4 var(--font-sans); }
.appsummary__field { font-weight: var(--weight-bold); }
</style>
