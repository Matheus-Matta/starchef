<script setup lang="ts">
/**
 * Zonas de entrega: taxa e prazo por faixa de distância.
 *
 * Os valores vêm de `DeliveryZone` no backend — taxa de entrega é regra de
 * negócio, não conteúdo do editor. Quem muda a taxa muda no cadastro, e o site
 * acompanha.
 */
import type { RenderNode } from '~~/types/builder'

defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()
const zones = computed(() => storefront.value.delivery.zones)
</script>

<template>
  <div :class="[...nodeClass, 'sf-info-grid']">
    <div v-for="zone in zones" :key="zone.id" class="sf-info-card">
      <div class="sf-info-card__label">{{ zone.name }}</div>
      <div>Até {{ zone.max_radius_km }} km</div>
      <div>Taxa: {{ formatPrice(zone.delivery_fee) || 'grátis' }}</div>
      <div>Aprox. {{ zone.estimated_minutes }} min</div>
    </div>

    <p v-if="!zones.length" class="sf-empty">Este restaurante não faz entregas no momento.</p>
  </div>
</template>
