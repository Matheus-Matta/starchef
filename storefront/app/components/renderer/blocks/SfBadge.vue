<script setup lang="ts">
/** Selo solto ("Mais vendido", "Novo"), fora do card de produto. */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const TONES = new Set(['sale', 'info', 'muted', 'accent'])
const tone = computed(() => {
  const value = String(props.node.props?.tone ?? 'accent')
  return TONES.has(value) ? value : 'accent'
})
const text = computed(() => String(props.node.props?.text ?? '') || props.node.content)
</script>

<template>
  <span v-if="text" :class="[...nodeClass, 'sf-badge', `sf-badge--${tone}`]" v-html="text" />
</template>
