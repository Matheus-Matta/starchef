<script setup lang="ts">
/**
 * Botão / link.
 *
 * Vira `<a>` quando tem destino e `<button>` quando não tem — um `<a>` sem
 * `href` não recebe foco pelo teclado, e o cliente que navega por Tab perde o
 * botão principal da página.
 */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const link = useSiteLink()

// O destino salvo no editor é relativo à raiz do SITE (`/promocoes`), porque é
// assim que o cliente pensa ao montar a página. O site mora em `/{slug}/`, e um
// caminho sem esse prefixo cairia na raiz do servidor. Âncoras (`#cardapio`),
// `tel:`, `mailto:` e URLs absolutas passam intactas.
const href = computed(() => link(props.node.attrs.href) || '')
const tag = computed(() => (props.node.attrs.href ? 'a' : 'button'))

// Link que abre em outra aba sem `noopener` dá à página de destino acesso ao
// `window.opener` do cardápio.
const relation = computed(() =>
  props.node.attrs.target === '_blank' ? (props.node.attrs.rel ?? 'noopener noreferrer') : props.node.attrs.rel,
)
</script>

<template>
  <component
    :is="tag"
    :class="nodeClass"
    v-bind="node.attrs"
    :href="tag === 'a' ? href : undefined"
    :rel="relation"
    :type="tag === 'button' ? 'button' : undefined"
  >
    <span v-if="node.content" v-html="node.content" />
    <SfNode v-for="child in node.children" :key="child.id" :node="child" />
  </component>
</template>
