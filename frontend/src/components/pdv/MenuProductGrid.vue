<template>
  <section class="catalogo">
    <div class="catalogo__filtros">
      <input
        v-model="busca"
        class="pdv-field"
        type="text"
        placeholder="Buscar produto por nome ou código…"
      />
      <div class="catalogo__categorias pdv-scroll">
        <button
          type="button"
          class="catalogo__categoria"
          :class="{ 'catalogo__categoria--ativa': !categoria }"
          @click="categoria = null"
        >
          Tudo
        </button>
        <button
          v-for="item in categorias"
          :key="item.id"
          type="button"
          class="catalogo__categoria"
          :class="{ 'catalogo__categoria--ativa': categoria === item.id }"
          @click="categoria = item.id"
        >
          {{ item.name }}
        </button>
      </div>
    </div>

    <div class="pdv-scroll catalogo__grade">
      <p v-if="carregando" class="pdv-empty">Carregando cardápio…</p>
      <p v-else-if="!visiveis.length" class="pdv-empty">Nenhum produto encontrado.</p>
      <button
        v-for="produto in visiveis"
        :key="produto.id"
        type="button"
        class="catalogo__produto"
        @click="$emit('pick', produto)"
      >
        <strong class="catalogo__nome">{{ produto.name }}</strong>
        <span class="catalogo__preco pdv-num">
          {{ dinheiro(produto.sale_price) }}
          <em v-if="produto.pricing_unit === 'kg'" class="catalogo__unidade">/kg</em>
        </span>
      </button>
    </div>
  </section>
</template>

<script setup>
/**
 * O cardápio da tela de Venda — o lado esquerdo do PDV.
 *
 * Toca o produto e ele cai no carrinho. Sem passo intermediário e sem abrir
 * pedido: é o gesto de um PDV de mercado, onde passar um item não compromete
 * nada até alguém fechar a compra.
 */
import { computed, ref } from "vue";

const props = defineProps({
  produtos: { type: Array, default: () => [] },
  categorias: { type: Array, default: () => [] },
  carregando: { type: Boolean, default: false },
});

defineEmits(["pick"]);

const busca = ref("");
const categoria = ref(null);

const visiveis = computed(() => {
  const termo = busca.value.trim().toLowerCase();
  return props.produtos.filter((produto) => {
    if (categoria.value && produto.category !== categoria.value) return false;
    if (!termo) return true;
    return [produto.name, produto.internal_code, produto.gtin]
      .filter(Boolean)
      .some((campo) => String(campo).toLowerCase().includes(termo));
  });
});

function dinheiro(valor) {
  return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
</script>

<style scoped>
.catalogo {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.catalogo__filtros {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.catalogo__categorias {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.catalogo__categoria {
  flex: 0 0 auto;
  padding: 6px 12px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 999px;
  background: transparent;
  color: var(--text-color-secondary, #6b7280);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.catalogo__categoria--ativa {
  border-color: var(--primary-color, #2563eb);
  color: var(--primary-color, #2563eb);
  font-weight: 700;
}

.catalogo__grade {
  flex: 1;
  display: grid;
  /* Alvo generoso: em boa parte das lojas esta tela roda em monitor com toque,
     e o operador acerta o produto de memória, sem mirar. */
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
  align-content: start;
}

.catalogo__produto {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 6px;
  min-height: 78px;
  padding: 10px;
  border: 1px solid var(--surface-border, #e5e7eb);
  border-radius: 8px;
  background: var(--surface-card, #fff);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.catalogo__nome {
  font-size: 13px;
  line-height: 1.25;
}

.catalogo__preco {
  font-size: 14px;
  font-weight: 700;
}

.catalogo__unidade {
  font-size: 11px;
  font-style: normal;
  font-weight: 400;
  color: var(--text-color-secondary, #6b7280);
}
</style>
