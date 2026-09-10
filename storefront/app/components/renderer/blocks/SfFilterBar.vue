<script setup lang="ts">
/**
 * Barra de filtros e ordenação acima da vitrine.
 *
 * Filtra em memória o que já veio no payload — nenhuma requisição por clique.
 * O estado é publicado por `provide` para a `sf-product-grid` da mesma página
 * consumir: os dois blocos são independentes no editor (o cliente pode
 * remover a barra), então a grade não pode DEPENDER dela para funcionar.
 */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()
const filter = useStorefrontFilter()

const showCategories = computed(() => props.node.props?.show_categories !== false)
const showSort = computed(() => props.node.props?.show_sort !== false)

const SORT_LABELS: Record<string, string> = {
  default: 'Relevância',
  name: 'Nome (A-Z)',
  price_asc: 'Menor preço',
  price_desc: 'Maior preço',
}

const sortOptions = computed(() => {
  const configured = props.node.props?.sort_options
  const keys = Array.isArray(configured) && configured.length
    ? configured.map((item) => String(item))
    : Object.keys(SORT_LABELS)
  return keys.filter((key) => SORT_LABELS[key]).map((key) => ({ value: key, label: SORT_LABELS[key]! }))
})

const categories = computed(() => storefront.value.categories.filter((category) => !category.parent_id))
</script>

<template>
  <div :class="[...nodeClass, 'sf-filterbar']">
    <div v-if="showCategories" class="sf-filterbar__chips">
      <button
        type="button"
        class="sf-chip"
        :class="{ 'sf-chip--active': !filter.categoryId.value }"
        @click="filter.setCategory('')"
      >
        Todas as categorias
      </button>
      <button
        v-for="category in categories"
        :key="category.id"
        type="button"
        class="sf-chip"
        :class="{ 'sf-chip--active': filter.categoryId.value === category.id }"
        @click="filter.setCategory(category.id)"
      >
        {{ category.name }}
      </button>
    </div>

    <label v-if="showSort" class="sf-filterbar__sort">
      <span>Ordenar por</span>
      <select :value="filter.sort.value" @change="filter.setSort(($event.target as HTMLSelectElement).value)">
        <option v-for="option in sortOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    </label>
  </div>
</template>
