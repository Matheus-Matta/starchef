<script setup lang="ts">
/**
 * Um nó do schema compilado.
 *
 * Resolve o componente pelo tipo e monta a classe de estilo que o compiler
 * gerou (`sf-n-<id>`). Tipo desconhecido não renderiza nada — o site do
 * restaurante nunca deve mostrar um bloco que o renderer não sabe desenhar.
 */
import type { RenderNode } from '~~/types/builder'
import { componentNameFor } from '~~/lib/builder/registry/renderer'
import { cssEscape } from '~~/lib/builder/compiler/compile-project'

const props = defineProps<{ node: RenderNode }>()

const resolved = computed(() => {
  const name = componentNameFor(props.node.type)
  return name ? resolveComponent(name) : null
})

const nodeClass = computed(() => [`sf-n-${cssEscape(props.node.id)}`, ...props.node.classes])
</script>

<template>
  <component :is="resolved" v-if="resolved" :node="node" :node-class="nodeClass" />
</template>
