<script setup lang="ts">
/** Espaço vertical. A altura vem do estilo do editor; 32px é só o piso. */
import type { RenderNode } from '~~/types/builder'

defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()
</script>

<template>
  <div :class="nodeClass" aria-hidden="true" style="min-height: 32px" />
</template>
