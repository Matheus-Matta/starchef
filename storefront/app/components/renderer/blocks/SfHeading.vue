<script setup lang="ts">
/** Título. A tag (`h1`…`h6`) vem do editor e importa para SEO e leitor de tela. */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const ALLOWED_TAGS = new Set(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
const tag = computed(() => (ALLOWED_TAGS.has(props.node.tag) ? props.node.tag : 'h2'))
</script>

<template>
  <!--
    O texto vai num `<span>` interno, e não em `v-html` no próprio elemento.
    O compilador do Vue trata `<component :is>` como componente e IGNORA um
    `v-html` aplicado nele — o título saía vazio na página, mesmo com o texto
    presente no conteúdo salvo. Num elemento real o `v-html` funciona.
  -->
  <component :is="tag" :class="nodeClass" v-bind="node.attrs">
    <span v-html="node.content" />
  </component>
</template>
