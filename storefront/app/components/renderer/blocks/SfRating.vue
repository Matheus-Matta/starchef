<script setup lang="ts">
/**
 * Nota em estrelas.
 *
 * O valor vem da configuração do bloco: o StarChef ainda não guarda avaliação
 * de cliente, e inventar uma nota a partir de outro dado seria mentir para o
 * consumidor. Quando existir avaliação de verdade, é aqui que ela entra.
 */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const value = computed(() => {
  const raw = Number(props.node.props?.value ?? 0)
  return Number.isFinite(raw) ? Math.min(Math.max(raw, 0), 5) : 0
})
const total = computed(() => Number(props.node.props?.total ?? 5) || 5)
</script>

<template>
  <span v-if="value > 0" :class="[...nodeClass, 'sf-rating']">
    <MaterialIcon name="star" :size="14" class="sf-rating__star" />
    <span class="sf-rating__value">{{ value.toFixed(1) }}/{{ total }}</span>
  </span>
</template>
