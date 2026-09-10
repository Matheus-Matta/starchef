<script setup lang="ts">
/**
 * Renderiza uma página do storefront a partir do conteúdo do editor.
 *
 * Recebe o payload público inteiro e compila o `page.data` uma vez. Os blocos
 * de dados (vitrine, categorias, horários) leem o payload por `inject` em vez
 * de receberem tudo por prop atravessando a árvore: um `sf-product-grid`
 * aninhado em quatro seções não deve obrigar cada nível a repassar produtos.
 *
 * O CSS do editor sai em um único `<style>` no SSR. Se fosse aplicado como
 * `style=""` inline, media query não funcionaria — e sem SSR do CSS a página
 * apareceria sem estilo por um instante antes de o JS assumir.
 */
import type { StorefrontPayload } from '~~/types/storefront'
import { compileProject } from '~~/lib/builder/compiler/compile-project'
import { STOREFRONT_KEY } from '~~/lib/builder/registry/injection'

const props = defineProps<{
  storefront: StorefrontPayload
}>()

const schema = computed(() => compileProject(props.storefront.page?.data))

const { cssVariables } = useStorefrontTheme(computed(() => props.storefront.site?.theme))

// Os blocos dinâmicos leem daqui. `computed` mantém a reatividade quando a
// navegação troca de página sem recriar o renderer.
provide(STOREFRONT_KEY, computed(() => props.storefront))

// Filtro/ordenação vivem no renderer, e não dentro da barra de filtros: a
// vitrine precisa enxergá-los, e os dois são blocos independentes que o
// cliente pode remover ou duplicar no editor.
provideStorefrontFilter()

useHead(() => ({
  style: schema.value.css ? [{ children: schema.value.css }] : [],
}))
</script>

<template>
  <div class="sf-root" :style="cssVariables">
    <!-- O cabeçalho vem do SITE, não da página: aparece em todas elas e o
         cliente não o apaga arrastando um bloco para fora do canvas. -->
    <StorefrontHeader :config="storefront.site?.header" />

    <SfNode v-for="node in schema.nodes" :key="node.id" :node="node" />

    <div v-if="!schema.nodes.length" class="sf-empty" style="margin: 64px auto; max-width: 520px">
      Esta página ainda não tem conteúdo publicado.
    </div>
  </div>
</template>
