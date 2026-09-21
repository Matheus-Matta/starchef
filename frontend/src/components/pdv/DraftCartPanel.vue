<template>
  <aside class="carrinho">
    <header class="carrinho__topo">
      <h2 class="pdv-page__title carrinho__titulo">Pedido</h2>
      <span class="pdv-muted">{{ quantidade }} {{ quantidade === 1 ? "item" : "itens" }}</span>
    </header>

    <!-- O "local para incluir a comanda" fica AQUI, no topo do carrinho: é um
         atributo do pedido que está sendo montado, na mesma altura em que o
         operador confere o que vai cobrar. -->
    <DraftCommandAttach
      :comandas="comandas"
      :mesa="mesa"
      :disabled="ocupado"
      @attach="$emit('attach', $event)"
      @detach="$emit('detach')"
    />

    <div class="pdv-scroll carrinho__itens">
      <p v-if="!itens.length" class="pdv-empty">
        Toque nos produtos para montar o pedido.
      </p>
      <DraftCartLine
        v-for="item in itens"
        :key="item._id"
        :item="item"
        :disabled="ocupado"
        @quantity="(delta) => $emit('quantity', item, delta)"
        @remove="$emit('remove', item)"
      />
    </div>

    <footer class="carrinho__rodape">
      <p class="carrinho__total">
        <span>Total</span>
        <strong class="pdv-num">{{ dinheiro(total) }}</strong>
      </p>
      <button
        class="pdv-btn"
        type="button"
        :disabled="ocupado || !itens.length"
        @click="$emit('kitchen')"
      >
        Enviar à cozinha
      </button>
      <button
        class="pdv-btn pdv-btn--primary"
        type="button"
        :disabled="ocupado || !itens.length"
        @click="$emit('pay')"
      >
        Ir para o pagamento
      </button>
      <!-- Os dois botões acima são os ÚNICOS que abrem pedido no servidor.
           Até um deles, isto aqui é um rascunho na memória da tela. -->
      <p class="pdv-muted carrinho__nota">
        O pedido é aberto ao enviar à cozinha ou ao ir para o pagamento.
      </p>
    </footer>
  </aside>
</template>

<script setup>
/**
 * O carrinho do rascunho — o lado direito da tela de Venda.
 *
 * Ele mostra o que ainda **não existe no servidor**. Os dois botões do rodapé
 * são os únicos que abrem pedido, e é essa a diferença que esta tela traz: até
 * tocar num deles, escolher produtos e anexar comanda não compromete nada.
 */
import DraftCartLine from "./DraftCartLine.vue";
import DraftCommandAttach from "./DraftCommandAttach.vue";

defineProps({
  itens: { type: Array, default: () => [] },
  comandas: { type: Array, default: () => [] },
  mesa: { type: Object, default: null },
  total: { type: Number, default: 0 },
  quantidade: { type: Number, default: 0 },
  ocupado: { type: Boolean, default: false },
});

defineEmits(["attach", "detach", "quantity", "remove", "kitchen", "pay"]);

function dinheiro(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
</script>

<style scoped>
.carrinho {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding: 14px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 10px;
  background: var(--surface-card, #fff);
  box-sizing: border-box;
}

.carrinho__topo {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.carrinho__titulo {
  font-size: 17px;
}

.carrinho__itens {
  flex: 1;
}

.carrinho__rodape {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--surface-border, #e5e7eb);
}

.carrinho__total {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin: 0;
  font-size: 14px;
}

.carrinho__total strong {
  font-size: 22px;
}

.carrinho__nota {
  margin: 0;
  text-align: center;
  line-height: 1.35;
}
</style>
