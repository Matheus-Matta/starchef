<script setup lang="ts">
/**
 * Lista de categorias do cardápio.
 *
 * Duas origens, escolhidas pelo trait "Menu":
 *
 * - **sem menu** (padrão): as categorias reais da conta, só as de raiz a
 *   menos que "Incluir subcategorias" esteja ligado;
 * - **com menu**: a curadoria de um `menu.Menu` vinculado — o restaurante
 *   escolhe QUAIS categorias aparecem e em que ordem, com título próprio se
 *   quiser (o mesmo menu que já alimenta a navegação do cabeçalho).
 *
 * O clique filtra a vitrine da página via `useStorefrontFilter` — o mesmo
 * estado compartilhado que a barra de filtros usa. Os dois são blocos
 * independentes (o cliente pode ter um sem o outro), e é esse estado no
 * renderer que os mantém em sincronia.
 */
import type { RenderNode } from '~~/types/builder'
import { propString, resolveCategories } from '~~/lib/storefront/resolve'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()
const filter = useStorefrontFilter()

const layout = computed(() => propString(props.node.props, 'layout', 'chips'))

// Mesma regra do canvas do editor: ver `lib/storefront/resolve`.
const categories = computed(() => resolveCategories(storefront.value, props.node.props))
</script>

<template>
  <nav
    :class="[...nodeClass, 'sf-categories', layout === 'list' ? 'sf-categories--list' : '']"
    aria-label="Categorias do cardápio"
  >
    <button
      v-for="category in categories"
      :key="category.id"
      type="button"
      class="sf-category-chip"
      :class="{ 'sf-category-chip--active': filter.categoryId.value === category.id }"
      @click="filter.setCategory(category.id)"
    >
      {{ category.name }}
    </button>

    <p v-if="!categories.length" class="sf-empty">Nenhuma categoria cadastrada ainda.</p>
  </nav>
</template>
