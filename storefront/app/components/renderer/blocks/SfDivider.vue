<script setup lang="ts">
/** Linha divisória. */
import type { RenderNode } from '~~/types/builder'

defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()
</script>

<template>
  <hr :class="nodeClass" style="border: 0; border-top: 1px solid var(--sf-border)">
</template>
