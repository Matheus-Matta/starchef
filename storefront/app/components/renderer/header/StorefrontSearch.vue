<script setup lang="ts">
/**
 * Busca do cabeçalho — o maior elemento da linha, ~45-50% da largura útil.
 *
 * Fundo cinza claro e **sem borda**: é o que a destaca contra o cabeçalho
 * branco. Uma busca branca com borda desapareceria no fundo e deixaria de
 * parecer o elemento principal.
 *
 * Filtra em memória o que já veio no payload — nenhuma requisição por tecla.
 * Com o catálogo inteiro em mãos, ir ao servidor só somaria latência.
 */
const props = defineProps<{
  placeholder?: string
  enabled?: boolean
}>()

const storefront = useStorefrontData()
const link = useSiteLink()
const term = ref('')
const focused = ref(false)

const results = computed(() => {
  const needle = term.value.trim().toLowerCase()
  if (needle.length < 2) return []
  return storefront.value.products
    .filter((product) => product.name.toLowerCase().includes(needle))
    .slice(0, 6)
})

// Fecha ao clicar fora seria o ideal; por ora o `blur` atrasado dá conta e
// mantém o clique no resultado funcionando (o blur dispara antes do click).
function onBlur() {
  setTimeout(() => (focused.value = false), 150)
}
</script>

<template>
  <div v-if="enabled !== false" class="sf-search">
    <span class="sf-search__icon" aria-hidden="true">
      <MaterialIcon name="search" :size="15" />
    </span>
    <input
      v-model="term"
      type="search"
      class="sf-search__input"
      :placeholder="placeholder || 'Buscar produtos e categorias'"
      :aria-label="placeholder || 'Buscar produtos e categorias'"
      @focus="focused = true"
      @blur="onBlur"
    >

    <ul v-if="focused && results.length" class="sf-search__results">
      <li v-for="product in results" :key="product.id">
        <a :href="link(`/produto/${product.id}`)">
          <img v-if="product.image" :src="product.image" :alt="product.name" loading="lazy">
          <span>{{ product.name }}</span>
          <strong>{{ formatPrice(product.current_price) }}</strong>
        </a>
      </li>
    </ul>
  </div>
</template>
