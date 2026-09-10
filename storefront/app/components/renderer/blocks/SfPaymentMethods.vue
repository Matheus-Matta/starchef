<script setup lang="ts">
/** Formas de pagamento aceitas — vêm do cadastro, não do editor. */
import type { RenderNode } from '~~/types/builder'

defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()
const methods = computed(() => storefront.value.payment_methods)
</script>

<template>
  <div :class="nodeClass" style="display: flex; flex-wrap: wrap; gap: 10px">
    <span v-for="method in methods" :key="method.id" class="sf-badge sf-badge--muted">
      {{ method.name }}
    </span>

    <p v-if="!methods.length" class="sf-empty">Formas de pagamento não cadastradas.</p>
  </div>
</template>
