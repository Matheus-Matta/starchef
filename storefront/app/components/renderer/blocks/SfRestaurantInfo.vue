<script setup lang="ts">
/** Endereço, telefone e e-mail do restaurante — tudo vindo do cadastro real. */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()

const showPhone = computed(() => props.node.props?.show_phone !== false)
const showAddress = computed(() => props.node.props?.show_address !== false)

const address = computed(() => {
  const parts = storefront.value.restaurant.address
  return [parts.street, parts.district, [parts.city, parts.state].filter(Boolean).join(' - '), parts.zip_code]
    .filter(Boolean)
    .join(', ')
})

const phone = computed(() => storefront.value.restaurant.phone)
const email = computed(() => storefront.value.restaurant.email)

// Telefone brasileiro em `tel:` precisa do país; sem ele o discador do celular
// erra o número em roaming.
const phoneHref = computed(() => `tel:+55${phone.value.replace(/\D/g, '')}`)
</script>

<template>
  <div :class="[...nodeClass, 'sf-info-grid']">
    <div v-if="showAddress && address" class="sf-info-card">
      <div class="sf-info-card__label">Endereço</div>
      <div>{{ address }}</div>
    </div>

    <div v-if="showPhone && phone" class="sf-info-card">
      <div class="sf-info-card__label">Telefone</div>
      <a :href="phoneHref">{{ phone }}</a>
    </div>

    <div v-if="email" class="sf-info-card">
      <div class="sf-info-card__label">E-mail</div>
      <a :href="`mailto:${email}`">{{ email }}</a>
    </div>
  </div>
</template>
