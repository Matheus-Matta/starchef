<script setup lang="ts">
/**
 * Faixa fina no topo: frete grátis, prazo, cupom.
 *
 * O texto vem da configuração do bloco, não de dado do restaurante — é
 * comunicação de campanha, e quem escreve é quem monta a página.
 */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const message = computed(() => String(props.node.props?.message ?? ''))
const dismissible = computed(() => props.node.props?.dismissible === true)
const hidden = ref(false)
</script>

<template>
  <div v-if="message && !hidden" :class="[...nodeClass, 'sf-announcement']">
    <span>{{ message }}</span>
    <button
      v-if="dismissible"
      type="button"
      class="sf-announcement__close"
      aria-label="Fechar aviso"
      @click="hidden = true"
    >
      <MaterialIcon name="close" :size="14" />
    </button>
  </div>
</template>
