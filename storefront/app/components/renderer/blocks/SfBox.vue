<script setup lang="ts">
/**
 * Bloco-caixa: seção, contêiner, linha, coluna, hero, banner.
 *
 * Todos compartilham o mesmo comportamento — uma tag, atributos, e filhos
 * dentro. O que os diferencia visualmente é o CSS que o cliente montou no
 * editor, não código nosso; escrever cinco componentes idênticos só criaria
 * cinco lugares para o mesmo bug aparecer.
 */
import type { RenderNode } from '~~/types/builder'

defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()
</script>

<template>
  <component :is="node.tag || 'div'" :class="nodeClass" v-bind="node.attrs">
    <!-- Texto rico só quando não há filhos: uma seção com blocos dentro não
         deve também despejar HTML solto. -->
    <span v-if="node.content && !node.children.length" v-html="node.content" />
    <SfNode v-for="child in node.children" :key="child.id" :node="child" />
  </component>
</template>
