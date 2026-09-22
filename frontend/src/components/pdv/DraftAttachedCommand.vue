<template>
  <div class="anexada">
    <span class="anexada__rotulo">
      Comanda <strong>{{ comanda.number }}</strong>
      <em v-if="comanda.pending_total" class="anexada__valor">
        {{ dinheiro(comanda.pending_total) }}
      </em>
    </span>
    <!-- O X, e não um "Retirar" escrito: ele mora no MODAL, ao lado da lista
         de onde a comanda saiu, então o gesto de tirar é o inverso exato do
         gesto de pôr. Ler o mesmo cartão no leitor também tira. -->
    <button
      class="anexada__soltar"
      type="button"
      :disabled="disabled"
      :aria-label="`Retirar comanda ${comanda.number}`"
      @click="$emit('detach')"
    >
      ✕
    </button>
  </div>
</template>

<script setup>
/**
 * Um cartão JÁ anexado, mostrado no topo do modal de incluir comanda.
 *
 * Ficava fora, empilhado acima do botão de anexar, e isso tinha dois
 * problemas: numa mesa com quatro cartões o carrinho começava com quatro
 * linhas antes do primeiro produto, e "incluir" ficava longe de "retirar" —
 * dois gestos opostos em lugares diferentes da tela.
 *
 * Aqui em cima da lista, o operador vê o que já está na conta e o que pode
 * entrar, no mesmo lugar.
 *
 * O valor fica ao lado do número porque é o que o cliente confere em voz alta
 * antes de pagar: numa conta com quatro cartões, "quanto é a minha?" é a
 * primeira pergunta.
 */
defineProps({
  comanda: { type: Object, required: true },
  disabled: { type: Boolean, default: false },
});

defineEmits(["detach"]);

function dinheiro(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}
</script>

<style scoped>
.anexada {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 10px;
  border: 1px solid var(--primary-color, #2563eb);
  border-radius: 8px;
  background: color-mix(in srgb, var(--primary-color, #2563eb) 8%, transparent);
}

.anexada__rotulo {
  font-size: 13px;
}

.anexada__valor {
  margin-left: 6px;
  font-style: normal;
  font-size: 11px;
  color: var(--text-color-secondary, #6b7280);
}

.anexada__soltar {
  flex: none;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-color-secondary, #6b7280);
  font: inherit;
  cursor: pointer;
}

.anexada__soltar:hover:not(:disabled) {
  background: var(--surface-hover, #f1f5f9);
  color: var(--red-600, #dc2626);
}
</style>
