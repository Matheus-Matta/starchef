<script setup lang="ts">
/**
 * Imagem do editor.
 *
 * `loading="lazy"` e `decoding="async"` por padrão: uma home de cardápio tem
 * facilmente uma dúzia de fotos, e carregar todas de uma vez adia o conteúdo
 * que o cliente veio ver. Sem `src` válido, nada é renderizado — um ícone de
 * imagem quebrada na página do restaurante é pior do que o espaço vazio.
 */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const source = computed(() => props.node.attrs.src ?? '')
</script>

<template>
  <img
    v-if="source"
    :class="nodeClass"
    v-bind="node.attrs"
    :src="source"
    :alt="node.attrs.alt ?? ''"
    loading="lazy"
    decoding="async"
  >
</template>
