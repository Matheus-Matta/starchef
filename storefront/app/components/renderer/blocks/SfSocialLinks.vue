<script setup lang="ts">
/**
 * Links de redes sociais.
 *
 * As URLs vêm da configuração do bloco e passam pelo sanitizador antes de ir
 * para o `href` — um `javascript:` num link de rede social é o caminho mais
 * curto para XSS na página pública.
 */
import type { RenderNode } from '~~/types/builder'
import { safeUrl } from '~~/lib/builder/security/sanitize'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const NETWORKS: Array<[string, string]> = [
  ['instagram', 'Instagram'],
  ['facebook', 'Facebook'],
  ['tiktok', 'TikTok'],
  ['x', 'X'],
  ['youtube', 'YouTube'],
]

const links = computed(() =>
  NETWORKS.map(([key, label]) => ({ key, label, href: safeUrl(props.node.props?.[key]) })).filter(
    (link) => link.href,
  ),
)
</script>

<template>
  <div :class="nodeClass" style="display: flex; flex-wrap: wrap; gap: 12px">
    <a
      v-for="link in links"
      :key="link.key"
      class="sf-category-chip"
      :href="link.href"
      target="_blank"
      rel="noopener noreferrer"
    >
      {{ link.label }}
    </a>
  </div>
</template>
