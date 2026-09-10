<script setup lang="ts">
/**
 * Busca no cardápio.
 *
 * Filtra em memória a lista que já veio no payload — nenhuma requisição por
 * tecla digitada. Com o catálogo inteiro em mãos, ir ao servidor só adicionaria
 * latência a um filtro que roda instantâneo no cliente.
 */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()
const term = ref('')

const placeholder = computed(() => String(props.node.props?.placeholder ?? 'Buscar no cardápio...'))

const results = computed(() => {
  const needle = term.value.trim().toLowerCase()
  if (needle.length < 2) return []
  return storefront.value.products
    .filter((product) => product.name.toLowerCase().includes(needle))
    .slice(0, 8)
})
</script>

<template>
  <div :class="nodeClass">
    <input
      v-model="term"
      type="search"
      :placeholder="placeholder"
      style="
        width: 100%;
        padding: 12px 16px;
        border: 1px solid var(--sf-border);
        border-radius: var(--sf-radius);
        background: var(--sf-background);
        color: var(--sf-text);
      "
    >

    <ul v-if="results.length" style="margin-top: 12px; display: flex; flex-direction: column; gap: 8px">
      <li v-for="product in results" :key="product.id" class="sf-hours__row">
        <span>{{ product.name }}</span>
        <span class="sf-hours__value">{{ formatPrice(product.current_price) }}</span>
      </li>
    </ul>
  </div>
</template>
