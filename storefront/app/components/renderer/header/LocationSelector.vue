<script setup lang="ts">
/**
 * Seletor de endereço de entrega: duas linhas, bem compactas.
 *
 * A hierarquia é o ponto — rótulo em 9-10px cinza, valor em 11-12px escuro. Ele
 * fica ao lado da marca e **não pode competir com a busca**, que é o maior
 * elemento do cabeçalho.
 *
 * Sem cidade configurada, o componente não aparece: um "Entregar em —" vazio
 * ocupa espaço e não informa nada.
 */
import type { StorefrontHeaderConfig } from '~~/types/storefront'

const props = defineProps<{ config?: StorefrontHeaderConfig['location'] }>()

const enabled = computed(() => props.config?.enabled !== false)
const label = computed(() => props.config?.label || 'Entregar em')
const value = computed(() => props.config?.value ?? '')
</script>

<template>
  <div v-if="enabled && value" class="sf-location">
    <span class="sf-location__icon" aria-hidden="true">
      <MaterialIcon name="location_on" :size="14" />
    </span>
    <span class="sf-location__text">
      <small>{{ label }}</small>
      <strong>{{ value }}</strong>
    </span>
  </div>
</template>
