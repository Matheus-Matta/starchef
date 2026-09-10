<script setup lang="ts">
/**
 * Ações do canto direito: carrinho e conta.
 *
 * Três formas de aparecer, escolhidas na aba Cabeçalho, porque loja nenhuma
 * concorda sobre isso:
 *
 * - `icon` — dois círculos coloridos de 34px. Ocupam pouco e são os únicos
 *   pontos de cor forte do cabeçalho branco;
 * - `icon_text` — o mesmo ícone com o rótulo ao lado, numa pílula. Ganha em
 *   clareza para quem não reconhece o ícone sozinho, e é o que a maioria das
 *   lojas grandes faz no desktop;
 * - `text` — só a palavra, sem ícone. Cabeçalho mais sóbrio, de marca.
 *
 * No celular o rótulo some em qualquer modo (ver `blocks.css`): a linha do
 * cabeçalho já divide espaço com marca e busca, e "Carrinho" por extenso
 * empurraria a busca para um talho inutilizável.
 *
 * O carrinho é visual nesta fase; o checkout é assunto de outra etapa.
 */
import type { StorefrontHeaderConfig } from '~~/types/storefront'

const props = defineProps<{ config?: StorefrontHeaderConfig['actions'] }>()

const showCart = computed(() => props.config?.cart !== false)
// `profile`, nunca `account`: o middleware de tenant do backend trata qualquer
// chave `account` do corpo como marcador de conta e bloqueia a resposta.
const showProfile = computed(() => props.config?.profile !== false)

const display = computed(() => props.config?.display ?? 'icon')
const withIcon = computed(() => display.value !== 'text')
const withLabel = computed(() => display.value !== 'icon')

const cartLabel = computed(() => props.config?.cart_label || 'Carrinho')
const profileLabel = computed(() => props.config?.profile_label || 'Entrar')
</script>

<template>
  <div class="sf-actions" :class="`sf-actions--${display}`">
    <button
      v-if="showCart"
      type="button"
      class="sf-actions__btn sf-actions__btn--cart"
      :aria-label="cartLabel"
    >
      <MaterialIcon v-if="withIcon" name="shopping_cart" :size="16" />
      <span v-if="withLabel" class="sf-actions__label">{{ cartLabel }}</span>
    </button>

    <button
      v-if="showProfile"
      type="button"
      class="sf-actions__btn sf-actions__btn--profile"
      :aria-label="profileLabel"
    >
      <MaterialIcon v-if="withIcon" name="person" :size="16" />
      <span v-if="withLabel" class="sf-actions__label">{{ profileLabel }}</span>
    </button>
  </div>
</template>
