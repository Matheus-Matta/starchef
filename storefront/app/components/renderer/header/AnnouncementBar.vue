<script setup lang="ts">
/**
 * Faixa promocional fina no topo — o primeiro dos três níveis do cabeçalho.
 *
 * É informação secundária de propósito: fonte pequena, altura de ~30px e um
 * único trecho em amarelo. Se competisse com a busca ou com a capa, roubaria
 * atenção da ação que de fato importa (comprar).
 *
 * O arredondamento só no topo (`14px 14px 0 0`) é o que faz o cabeçalho inteiro
 * parecer um cartão apoiado sobre o fundo creme, em vez de uma barra colada na
 * borda da janela.
 */
import type { StorefrontHeaderConfig } from '~~/types/storefront'

const props = defineProps<{ config?: StorefrontHeaderConfig['announcement'] }>()

const enabled = computed(() => props.config?.enabled !== false)
const text = computed(() => props.config?.text ?? '')
const highlight = computed(() => props.config?.highlight ?? '')
const secondary = computed(() => props.config?.secondary ?? '')
const url = computed(() => props.config?.url ?? '')

const hasContent = computed(() => Boolean(text.value || highlight.value || secondary.value))
</script>

<template>
  <div v-if="enabled && hasContent" class="sf-announce">
    <component :is="url ? 'a' : 'div'" :href="url || undefined" class="sf-announce__inner">
      <span v-if="highlight" class="sf-announce__highlight">{{ highlight }}</span>
      <span v-if="text">{{ text }}</span>
      <!-- Separador decorativo entre as duas mensagens: some junto com a
           segunda no celular, onde não há largura para as duas. -->
      <span v-if="text && secondary" class="sf-announce__sep" aria-hidden="true">✦</span>
      <span v-if="secondary" class="sf-announce__secondary">{{ secondary }}</span>
    </component>
  </div>
</template>
