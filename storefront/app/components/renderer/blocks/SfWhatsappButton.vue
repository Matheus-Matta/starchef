<script setup lang="ts">
/**
 * Botão flutuante de WhatsApp.
 *
 * Usa o telefone do cadastro do restaurante quando o bloco não traz um. Sem
 * número em lugar nenhum, o botão não aparece — um botão que abre uma conversa
 * com ninguém é pior do que botão nenhum.
 */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()

const digits = computed(() => {
  const configured = String(props.node.props?.phone ?? '')
  const raw = configured || storefront.value.restaurant.phone || ''
  const cleaned = raw.replace(/\D/g, '')
  if (!cleaned) return ''
  return cleaned.startsWith('55') ? cleaned : `55${cleaned}`
})

const label = computed(() => String(props.node.props?.label ?? 'Pedir no WhatsApp'))
const message = computed(() => String(props.node.props?.message ?? ''))

// `floating` gruda o botão no canto da tela; `inline` o deixa correr com o
// resto da página. A prop já existia e o editor já a oferecia, mas o
// componente a ignorava — o botão ficava flutuando nas duas opções, e mudar o
// campo não fazia nada no site publicado.
const floating = computed(() => String(props.node.props?.position ?? 'floating') !== 'inline')

const href = computed(() => {
  if (!digits.value) return ''
  const text = message.value ? `?text=${encodeURIComponent(message.value)}` : ''
  return `https://wa.me/${digits.value}${text}`
})
</script>

<template>
  <a
    v-if="href"
    :class="[...nodeClass, 'sf-floating-button', { 'sf-floating-button--inline': !floating }]"
    :href="href"
    target="_blank"
    rel="noopener noreferrer"
  >
    <MaterialIcon name="chat" :size="18" />
    {{ label }}
  </a>
</template>
