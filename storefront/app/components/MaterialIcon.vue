<script setup lang="ts">
/**
 * Um ícone do Material Symbols — usado no site publicado e nos painéis do
 * editor. Ver `lib/icons/material-icons.ts` para o porquê do pacote e de
 * extrair só o `d` do `<path>`.
 *
 * A cor vem de fora (`fill: currentColor`, herdado do CSS do elemento pai) —
 * é o que faz o MESMO ícone servir a um botão verde e a um cinza sem duas
 * variantes. `size` aceita número (vira `px`) ou qualquer unidade CSS.
 */
import { materialIconPath, type MaterialIconName } from '~~/lib/icons/material-icons'

const props = withDefaults(defineProps<{ name: MaterialIconName; size?: number | string }>(), {
  size: 20,
})

const dimension = computed(() => (typeof props.size === 'number' ? `${props.size}px` : props.size))
const d = computed(() => materialIconPath(props.name))
</script>

<template>
  <svg
    class="sf-icon"
    viewBox="0 0 24 24"
    :width="dimension"
    :height="dimension"
    fill="currentColor"
    aria-hidden="true"
    focusable="false"
  >
    <path :d="d" />
  </svg>
</template>

<style scoped>
/* `display: block` evita o respiro de 4-5px que todo <svg> inline ganha por
   ser tratado como texto (baseline) — o mesmo ajuste que um <img> pede. */
.sf-icon {
  display: block;
  flex-shrink: 0;
}
</style>
