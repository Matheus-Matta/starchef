<template>
  <section class="grupo">
    <header class="grupo__cabecalho">
      <div>
        <h3 class="grupo__titulo">Comanda {{ group.number }}</h3>
        <p v-if="tableNumber" class="grupo__mesa">Mesa {{ tableNumber }}</p>
      </div>
      <div class="grupo__direita">
        <strong class="grupo__total">{{ money(group.total) }}</strong>
        <button
          class="grupo__remover"
          type="button"
          :disabled="disabled"
          title="Imprimir a conferência desta comanda (não é nota fiscal)"
          @click="$emit('receipt', group.commandId)"
        >
          Conferência
        </button>
        <button
          v-if="removable"
          class="grupo__remover"
          type="button"
          :disabled="disabled"
          @click="$emit('remove', group.commandId)"
        >
          Retirar
        </button>
      </div>
    </header>

    <ul class="grupo__itens">
      <li v-for="item in group.items" :key="item.id" class="grupo__item">
        <span class="grupo__quantidade">{{ quantity(item) }}</span>
        <span class="grupo__produto">
          {{ item.product_name }}
          <em v-if="item.customer_note" class="grupo__obs">{{ item.customer_note }}</em>
        </span>
        <span class="grupo__valor">{{ money(item.total_price) }}</span>
      </li>
    </ul>
  </section>
</template>

<script setup>
/**
 * Os itens de UMA comanda dentro da conta agrupada.
 *
 * A conferência com o cliente acontece item a item, em voz alta: é ela que
 * pega o engano antes de virar discussão. E com quatro comandas numa conta,
 * "de quem é isto" é a pergunta que o cliente faz — por isso a lista é
 * agrupada por comanda, e não uma lista corrida de produtos.
 */
const props = defineProps({
  group: { type: Object, required: true },
  tableNumber: { type: [String, Number], default: null },
  removable: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
});

// `receipt` é o papel que o cliente pede — "e a comanda 13, quanto deu?" —
// dentro de uma conta de quatro pessoas. Não é nota fiscal: a NFC-e é uma só,
// do pedido consolidado.
defineEmits(["remove", "receipt"]);

function money(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Produto por quilo mostra o peso; o resto mostra a contagem. */
function quantity(item) {
  const bruto = Number(item.quantity || 0);
  if (!Number.isInteger(bruto)) return `${bruto.toFixed(3)} kg`;
  return `${bruto}x`;
}

defineExpose({ group: props.group });
</script>

<style scoped>
.grupo {
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 10px;
  background: var(--surface-card, #fff);
  overflow: hidden;
}

.grupo__cabecalho {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  background: var(--surface-ground, #f6f7f9);
  border-bottom: 1px solid var(--surface-border, #e5e7eb);
}

.grupo__titulo {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.grupo__mesa {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-color-secondary, #6b7280);
}

.grupo__direita {
  display: flex;
  align-items: center;
  gap: 12px;
}

.grupo__total {
  font-size: 16px;
  font-variant-numeric: tabular-nums;
}

.grupo__remover {
  border: 1px solid var(--surface-border, #e5e7eb);
  background: transparent;
  color: var(--text-color-secondary, #6b7280);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
}

.grupo__remover:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.grupo__itens {
  list-style: none;
  margin: 0;
  padding: 0;
}

.grupo__item {
  display: grid;
  grid-template-columns: 64px 1fr auto;
  gap: 10px;
  align-items: baseline;
  padding: 8px 14px;
  border-bottom: 1px solid var(--surface-border, #f1f2f4);
  font-size: 14px;
}

.grupo__item:last-child {
  border-bottom: 0;
}

.grupo__quantidade {
  font-variant-numeric: tabular-nums;
  color: var(--text-color-secondary, #6b7280);
}

.grupo__obs {
  display: block;
  font-size: 12px;
  font-style: normal;
  color: var(--text-color-secondary, #6b7280);
}

.grupo__valor {
  font-variant-numeric: tabular-nums;
}
</style>
