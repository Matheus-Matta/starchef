<script setup lang="ts">
/** Parágrafo / texto rico. O HTML já foi sanitizado no compiler. */
import type { RenderNode } from '~~/types/builder'

defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()
</script>

<template>
  <component :is="node.tag || 'p'" :class="nodeClass" v-bind="node.attrs">
    <span v-html="node.content" />
    <SfNode v-for="child in node.children" :key="child.id" :node="child" />
  </component>
</template>
