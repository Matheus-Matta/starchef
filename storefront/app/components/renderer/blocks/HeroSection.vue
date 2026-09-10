<script setup lang="ts">
/**
 * `sf-hero` — a capa promocional da home.
 *
 * É um bloco de CONFIGURAÇÃO, não um contêiner: título, destaque, descrição,
 * botão, imagem e medidas são props que o editor expõe como campos. Montar a
 * capa com um título, um texto e um botão soltos dentro pareceria mais
 * flexível, mas quebra fácil — basta arrastar o botão para fora e a capa fica
 * sem chamada para ação, e quem descobre é o cliente, depois de publicar.
 *
 * As medidas têm variante por dispositivo porque a mesma capa que respira em
 * 1360px sufoca em 375px. Elas viram variáveis CSS no elemento (`--sf-hero-*`)
 * e o `storefront.css` decide qual vale em cada faixa: media query não existe
 * em `style=""` inline, então a alternativa seria gerar CSS por instância.
 *
 * Nenhum texto de restaurante aqui dentro — tudo chega por prop.
 *
 * **Uma capa ou várias.** Sem menu vinculado, a capa é uma só, montada com as
 * props do bloco. Com um menu vinculado, cada ITEM daquele menu vira um slide
 * — e a capa passa a ser um carrossel de banners com setas e pontinhos.
 *
 * O menu foi a escolha em vez de uma lista de slides dentro do próprio bloco
 * por dois motivos: `menu.MenuItem` já tem o tipo "Imagem / banner" com foto,
 * título, subtítulo e link (é para isso que ele existe), e o painel de traits
 * do GrapesJS não tem campo repetível — uma lista de objetos ali viraria um
 * JSON digitado à mão. Assim o restaurante monta os banners no cadastro de
 * Menus, com upload de imagem de verdade, e o bloco só aponta.
 */
import type { RenderNode } from '~~/types/builder'
import { resolveHeroSlides } from '~~/lib/storefront/resolve'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const link = useSiteLink()
const storefront = useStorefrontData()

function str(key: string, fallback = ''): string {
  const value = props.node.props?.[key]
  return typeof value === 'string' && value.trim() ? value : fallback
}

// Mesma regra do canvas do editor: ver `lib/storefront/resolve`.
const slides = computed(() => resolveHeroSlides(storefront.value, props.node.props))

const current = ref(0)
const isCarousel = computed(() => slides.value.length > 1)
// `slides` encolhe quando o menu perde itens: sem isto, o índice apontaria
// para um slide que não existe mais e a capa ficaria em branco.
watch(slides, (value) => { if (current.value >= value.length) current.value = 0 })

const slide = computed(() => slides.value[current.value] ?? slides.value[0])

function go(direction: 1 | -1) {
  const total = slides.value.length
  // Circular: da última volta para a primeira. Um carrossel que trava na ponta
  // faz o visitante achar que quebrou.
  current.value = (current.value + direction + total) % total
}

const title = computed(() => slide.value?.title ?? '')
const highlight = computed(() => slide.value?.highlight ?? '')
const description = computed(() => slide.value?.description ?? '')
const ctaLabel = computed(() => slide.value?.ctaLabel ?? '')
const ctaUrl = computed(() => slide.value?.ctaUrl ?? '#')
const image = computed(() => slide.value?.image ?? '')
const background = computed(() => str('background'))
const decorations = computed(() => props.node.props?.decorations !== false)

// `right-bottom`, `right-center`, `left-bottom`, `left-center`: o lado decide a
// ordem das colunas; o encaixe vertical decide se a foto "senta" na base da
// capa (produto apoiado) ou fica centrada.
const position = computed(() => str('image_position', 'right-bottom'))
const side = computed(() => (position.value.startsWith('left') ? 'left' : 'right'))
const anchor = computed(() => (position.value.endsWith('center') ? 'center' : 'bottom'))

const align = computed(() => str('align', 'left'))
const alignMobile = computed(() => str('align_mobile', align.value))

const cssVars = computed(() => ({
  '--sf-hero-height': str('height', '350px'),
  '--sf-hero-height-tablet': str('height_tablet', str('height', '300px')),
  '--sf-hero-height-mobile': str('height_mobile', 'auto'),
  '--sf-hero-padding': str('padding', '56px'),
  '--sf-hero-padding-mobile': str('padding_mobile', '32px'),
  '--sf-hero-image-width': str('image_width', '52%'),
  ...(background.value ? { '--sf-hero-bg': background.value } : {}),
}))
</script>

<template>
  <section
    :class="[
      ...nodeClass,
      'sf-hero',
      `sf-hero--image-${side}`,
      `sf-hero--anchor-${anchor}`,
      `sf-hero--align-${align}`,
      `sf-hero--align-mobile-${alignMobile}`,
      { 'sf-hero--has-image': image },
    ]"
    :style="cssVars"
    v-bind="node.attrs"
  >
    <!-- Círculos concêntricos atrás da foto: são o que impede a capa de virar
         um retângulo verde chapado. Puramente decorativos, somem com a prop. -->
    <div v-if="decorations" class="sf-hero__decor" aria-hidden="true">
      <span class="sf-hero__circle sf-hero__circle--lg" />
      <span class="sf-hero__circle sf-hero__circle--md" />
    </div>

    <div class="sf-hero__content">
      <h1 v-if="title || highlight" class="sf-hero__title">
        {{ title }}
        <em v-if="highlight" class="sf-hero__highlight">{{ highlight }}</em>
      </h1>

      <p v-if="description" class="sf-hero__description">{{ description }}</p>

      <a v-if="ctaLabel" class="sf-hero__cta" :href="link(ctaUrl)">
        {{ ctaLabel }}
        <MaterialIcon name="arrow_forward" :size="16" />
      </a>
    </div>

    <template v-if="isCarousel">
      <button type="button" class="sf-hero__arrow sf-hero__arrow--prev" aria-label="Banner anterior" @click="go(-1)">
        <MaterialIcon name="chevron_left" :size="20" />
      </button>
      <button type="button" class="sf-hero__arrow sf-hero__arrow--next" aria-label="Próximo banner" @click="go(1)">
        <MaterialIcon name="chevron_right" :size="20" />
      </button>

      <div class="sf-hero__dots">
        <button
          v-for="(item, index) in slides"
          :key="item.id"
          type="button"
          class="sf-hero__dot"
          :class="{ 'is-active': index === current }"
          :aria-label="`Banner ${index + 1}`"
          @click="current = index"
        />
      </div>
    </template>

    <div v-if="image" class="sf-hero__media">
      <img :src="image" :alt="title || ''" loading="eager">
    </div>
  </section>
</template>
