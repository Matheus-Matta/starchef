<script setup lang="ts">
/**
 * Horários de funcionamento da unidade.
 *
 * O `opening_hours` da filial é um JSON livre no backend, preenchido pela
 * retaguarda — este bloco aceita as duas formas que aparecem na prática
 * (`"09:00-18:00"` e `{open, close}`) e ignora o que não reconhecer, em vez de
 * quebrar a página por causa de um formato inesperado.
 */
import type { RenderNode } from '~~/types/builder'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()

const DAYS: Array<[string, string]> = [
  ['monday', 'Segunda'],
  ['tuesday', 'Terça'],
  ['wednesday', 'Quarta'],
  ['thursday', 'Quinta'],
  ['friday', 'Sexta'],
  ['saturday', 'Sábado'],
  ['sunday', 'Domingo'],
]

const highlightToday = computed(() => props.node.props?.highlight_today !== false)
const todayKey = computed(() => DAYS[(new Date().getDay() + 6) % 7]?.[0] ?? '')

function describe(value: unknown): string {
  if (!value) return 'Fechado'
  if (typeof value === 'string') return value
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    if (record.closed === true) return 'Fechado'
    if (record.open && record.close) return `${record.open} às ${record.close}`
  }
  return ''
}

const rows = computed(() => {
  // A PRIMEIRA unidade que tenha horário cadastrado — não simplesmente a
  // primeira da lista. Uma conta costuma ter uma filial criada junto com o
  // restaurante e ainda sem horários; pegando a primeira às cegas, o site
  // anunciava "Fechado" nos sete dias com a unidade de verdade aberta ao lado.
  const branch = storefront.value.opening_hours.find(
    (item) => item.hours && Object.keys(item.hours).length > 0,
  )
  const hours = (branch?.hours ?? {}) as Record<string, unknown>
  return DAYS.map(([key, label]) => ({ key, label, value: describe(hours[key]) })).filter(
    (row) => row.value,
  )
})
</script>

<template>
  <div :class="[...nodeClass, 'sf-hours']">
    <div
      v-for="row in rows"
      :key="row.key"
      class="sf-hours__row"
      :class="{ 'sf-hours__row--today': highlightToday && row.key === todayKey }"
    >
      <span class="sf-hours__day">{{ row.label }}</span>
      <span class="sf-hours__value">{{ row.value }}</span>
    </div>

    <p v-if="!rows.length" class="sf-empty">Horários ainda não cadastrados.</p>
  </div>
</template>
