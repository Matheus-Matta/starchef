<script setup lang="ts">
/**
 * Cabeçalho global do site — os três níveis montados.
 *
 * Vive no SITE (`MenuSite.header`) e não na página: aparece em todas elas e o
 * cliente não consegue apagá-lo por engano arrastando um bloco para fora do
 * canvas. O que ele configura são as opções (faixa, endereço, busca, ações,
 * menus); a estrutura é nossa.
 *
 * Os três níveis, de cima para baixo:
 *
 *   1. faixa promocional escura, de ponta a ponta da janela;
 *   2. linha principal — marca, endereço, busca (o maior elemento) e ações;
 *   3. barra de navegação compacta.
 *
 * O cabeçalho é FULL WIDTH e sem cartão: não tem raio nem fundo próprio, e
 * fica direto sobre o creme da página — só o conteúdo de cada nível (o texto
 * da faixa, a linha principal, a nav) fica preso ao container de 1360px. É a
 * busca, com fundo branco, que se destaca contra esse fundo.
 *
 * Nada de conteúdo fixo aqui: marca, textos e menus chegam por `config`.
 */
import type { StorefrontHeaderConfig } from '~~/types/storefront'

const props = defineProps<{ config?: StorefrontHeaderConfig }>()

const storefront = useStorefrontData()
// Todo link interno passa por aqui: o site vive sob `/{slug}/`, e um `href="/"`
// cru levaria o visitante para a raiz do servidor — ou para a loja de outro.
const link = useSiteLink()

const config = computed<StorefrontHeaderConfig>(() => props.config ?? {})
const sticky = computed(() => config.value.sticky !== false)

// A marca cai para o nome do site e, por último, para o do restaurante: um
// cabeçalho sem identificação nenhuma é pior que um com o nome repetido.
const brand = computed(
  () => config.value.brand_name || storefront.value.site.name || storefront.value.restaurant.name,
)
const logo = computed(
  () => config.value.logo_url || storefront.value.site.theme?.logoUrl || storefront.value.restaurant.logo,
)
</script>

<template>
  <header class="sf-site-header" :class="{ 'sf-site-header--sticky': sticky }">
    <div class="sf-site-header__card">
      <AnnouncementBar :config="config.announcement" />

      <div class="sf-site-header__main">
        <a class="sf-site-header__brand" :href="link('/')">
          <img v-if="logo" :src="logo" :alt="brand" class="sf-site-header__logo">
          <span v-else>{{ brand }}</span>
        </a>

        <LocationSelector :config="config.location" />

        <StorefrontSearch
          class="sf-site-header__search"
          :enabled="config.search?.enabled"
          :placeholder="config.search?.placeholder"
        />

        <HeaderActions :config="config.actions" />
      </div>

      <StorefrontNav :primary="config.nav_menu" :secondary="config.secondary_menu" />
    </div>
  </header>
</template>
