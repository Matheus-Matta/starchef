<template>
  <div class="linha">
    <div class="linha__produto">
      <strong>{{ item.product_name }}</strong>
      <em v-if="item.customer_note" class="pdv-muted linha__obs">{{ item.customer_note }}</em>
    </div>
    <div class="linha__quantidade">
      <button type="button" :disabled="disabled" @click="$emit('quantity', -1)">−</button>
      <span class="pdv-num">{{ rotulo }}</span>
      <!-- Produto por peso não tem `+`: a quantidade vem da balança, não do
           teclado — a mesma regra que o backend aplica em `set_item_quantity`. -->
      <button
        type="button"
        :disabled="disabled || item.pricing_unit === 'kg'"
        @click="$emit('quantity', 1)"
      >
        +
      </button>
    </div>
    <span class="pdv-num linha__valor">{{ valor }}</span>
    <button class="linha__remover" type="button" :disabled="disabled" @click="$emit('remove')">
      ✕
    </button>
  </div>
</template>

<script setup>
/** Uma linha do carrinho em rascunho. */
import { computed } from "vue";

const props = defineProps({
  item: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
});

defineEmits(["quantity", "remove"]);

/** Produto por quilo mostra o peso; o resto mostra a contagem. */
const rotulo = computed(() => {
  const bruto = Number(props.item.quantity || 0);
  return props.item.pricing_unit === "kg" ? `${bruto.toFixed(3)} kg` : `${bruto}`;
});

const valor = computed(() =>
  (Number(props.item.unit_price || 0) * Number(props.item.quantity || 0)).toLocaleString(
    "pt-BR",
    { style: "currency", currency: "BRL" },
  ),
);
</script>

<style scoped>
.linha {
  display: grid;
  grid-template-columns: 1fr auto auto 24px;
  gap: 8px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--surface-border, #f1f2f4);
  font-size: 13px;
}

.linha__obs {
  display: block;
  font-size: 11px;
  font-style: normal;
}

.linha__quantidade {
  display: flex;
  align-items: center;
  gap: 6px;
}

.linha__quantidade button {
  width: 26px;
  height: 26px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.linha__valor {
  font-weight: 600;
}

.linha__remover {
  border: 0;
  background: transparent;
  color: var(--text-color-secondary, #6b7280);
  cursor: pointer;
  font: inherit;
}
</style>
