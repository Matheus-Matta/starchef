<script setup lang="ts">
/**
 * Vitrine de produtos — o bloco central do cardápio.
 *
 * Serve também a `sf-featured-products`, `sf-promotions` e
 * `sf-product-carousel`: os quatro mostram a mesma lista com filtros
 * diferentes, e a configuração salva no editor é que decide qual. Manter um
 * componente só significa que um ajuste no card de produto vale para todos.
 *
 * O bloco NÃO guarda produto nenhum: `props` traz só categoria, ordenação,
 * limite e o que exibir. Nome, preço e foto vêm do payload público, então um
 * preço alterado no PDV aparece no site sem ninguém reabrir o editor.
 *
 * A barra de filtros (`sf-filter-bar`), quando existe na página, tem
 * precedência sobre a categoria/ordenação salvas no bloco — é uma escolha que
 * o visitante acabou de fazer, e ela vence a configuração de montagem.
 *
 * O botão é visual nesta fase — o carrinho é assunto de uma etapa posterior.
 */
import type { RenderNode } from '~~/types/builder'
import { columnCount, propBool, propString, resolveShowcaseProducts, showcaseLayout } from '~~/lib/storefront/resolve'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()
const filter = useStorefrontFilter()

const config = computed(() => {
  const raw = props.node.props ?? {}
  return {
    showImage: propBool(raw, 'show_image', true),
    showDescription: propBool(raw, 'show_description', false),
    showPrice: propBool(raw, 'show_price', true),
    showOldPrice: propBool(raw, 'show_old_price', true),
    showButton: propBool(raw, 'show_button', true),
    showBadges: propBool(raw, 'show_badges', true),
    showRating: propBool(raw, 'show_rating', false),
    cardStyle: propString(raw, 'card_style', 'market'),
    desktop: columnCount(raw, 'desktop', 4),
    tablet: columnCount(raw, 'tablet', 2),
    mobile: columnCount(raw, 'mobile', 2),
  }
})

// Quem decide o que aparece é `lib/storefront/resolve` — o MESMO módulo que a
// prévia do canvas do editor chama. Enquanto a regra morava aqui dentro, a
// prévia tinha a própria versão dela, e as duas divergiam: o editor mostrava
// uma vitrine cheia onde o site publicava uma vazia.
const products = computed(() =>
  resolveShowcaseProducts(storefront.value, props.node.props, props.node.type, {
    // A escolha do visitante na barra de filtros vence a do bloco.
    categoryId: filter.categoryId.value,
    sort: filter.sort.value,
  }),
)

const isCarousel = computed(() => showcaseLayout(props.node.props, props.node.type) === 'carousel')

/** Desconto em % — só quando existe preço promocional de verdade. */
function discountPercent(product: { price: string | null; promotional_price: string | null }): number {
  // A ausência de promoção precisa ser testada ANTES da conversão: a API manda
  // `null` nesse caso, e `Number(null)` é 0 — o que fazia todo produto sem
  // promoção exibir "-100%", como se estivesse sendo dado de graça.
  if (product.promotional_price === null || product.promotional_price === undefined || product.promotional_price === '') {
    return 0
  }
  const full = Number(product.price)
  const promo = Number(product.promotional_price)
  if (!Number.isFinite(full) || !Number.isFinite(promo) || full <= 0 || promo >= full) return 0
  return Math.round(((full - promo) / full) * 100)
}

// As colunas viram variáveis CSS em vez de classe: o valor é escolhido pelo
// cliente no editor, e uma classe gerada dinamicamente (`grid-cols-[7]`) não
// existiria no CSS produzido no build.
const gridStyle = computed(() => ({
  '--sf-grid-desktop': String(config.value.desktop),
  '--sf-grid-tablet': String(config.value.tablet),
  '--sf-grid-mobile': String(config.value.mobile),
}))

/**
 * Carrossel: uma faixa que rola na horizontal, com setas nas pontas.
 *
 * Rolagem nativa (`overflow-x` + `scroll-snap`), e não um `transform` com
 * índice controlado por JS. Duas razões práticas: no celular o gesto de
 * arrastar já funciona sem escrever uma linha, e a faixa continua acessível
 * pelo teclado e pela roda do mouse. As setas são um atalho para quem está no
 * desktop, não o único caminho.
 */
const track = ref<HTMLElement | null>(null)
const atStart = ref(true)
const atEnd = ref(false)

function updateArrows() {
  const el = track.value
  if (!el) return
  atStart.value = el.scrollLeft <= 1
  // A margem de 1px absorve o arredondamento do navegador: sem ela, a seta da
  // direita continuava acesa no fim da faixa em telas com zoom fracionário.
  atEnd.value = el.scrollLeft + el.clientWidth >= el.scrollWidth - 1
}

function scrollByPage(direction: 1 | -1) {
  const el = track.value
  if (!el) return
  // Rola quase a largura visível, e não ela inteira: sobra um cartão à vista,
  // que é o que diz ao olho que a faixa continua.
  el.scrollBy({ left: direction * el.clientWidth * 0.85, behavior: 'smooth' })
}

onMounted(() => {
  updateArrows()
  window.addEventListener('resize', updateArrows)
})

onBeforeUnmount(() => window.removeEventListener('resize', updateArrows))

// A lista muda quando o visitante filtra por categoria: as setas precisam ser
// recalculadas, senão a da direita fica acesa numa faixa que já cabe inteira.
watch(products, () => nextTick(updateArrows))
</script>

<template>
  <div :class="[...nodeClass, isCarousel ? 'sf-showcase--carousel' : '']">
    <div v-if="products.length && isCarousel" class="sf-carousel">
      <button
        type="button"
        class="sf-carousel__arrow sf-carousel__arrow--prev"
        :disabled="atStart"
        aria-label="Anterior"
        @click="scrollByPage(-1)"
      >
        <MaterialIcon name="chevron_left" :size="20" />
      </button>

      <div ref="track" class="sf-carousel__track" :style="gridStyle" @scroll.passive="updateArrows">
        <article
          v-for="product in products"
          :key="product.id"
          class="sf-product-card"
          :class="`sf-product-card--${config.cardStyle}`"
        >
          <div class="sf-product-card__media">
            <img
              v-if="config.showImage && product.image"
              class="sf-product-card__image"
              :src="product.image"
              :alt="product.name"
              loading="lazy"
              decoding="async"
            >
            <div v-else-if="config.showImage" class="sf-product-card__image sf-product-card__image--empty" aria-hidden="true" />

            <div v-if="config.showBadges" class="sf-product-card__badges">
              <span v-if="discountPercent(product)" class="sf-badge sf-badge--sale">
                -{{ discountPercent(product) }}%
              </span>
              <span v-if="product.is_weighed" class="sf-badge sf-badge--info">por kg</span>
              <span v-if="!product.available_for_delivery" class="sf-badge sf-badge--muted">só retirada</span>
            </div>
          </div>

          <div class="sf-product-card__body">
            <h3 class="sf-product-card__name">{{ product.name }}</h3>

            <p v-if="config.showDescription && product.description" class="sf-product-card__description">
              {{ product.description }}
            </p>

            <div v-if="config.showRating" class="sf-rating" aria-hidden="true">
              <MaterialIcon name="star" :size="14" class="sf-rating__star" />
              <span class="sf-rating__value">{{ product.preparation_minutes ? `${product.preparation_minutes} min` : "Novo" }}</span>
            </div>

            <div class="sf-product-card__foot">
              <div v-if="config.showPrice" class="sf-product-card__price">
                <span>{{ formatPrice(product.current_price) }}</span>
                <span v-if="config.showOldPrice && product.promotional_price" class="sf-product-card__price-was">
                  {{ formatPrice(product.price) }}
                </span>
              </div>

              <button
                v-if="config.showButton"
                type="button"
                class="sf-product-card__add"
                :aria-label="`Adicionar ${product.name}`"
              >
                +
              </button>
            </div>
          </div>
        </article>
      </div>

      <button
        type="button"
        class="sf-carousel__arrow sf-carousel__arrow--next"
        :disabled="atEnd"
        aria-label="Próximo"
        @click="scrollByPage(1)"
      >
        <MaterialIcon name="chevron_right" :size="20" />
      </button>
    </div>

    <div v-else-if="products.length" class="sf-product-grid" :style="gridStyle">
      <article
        v-for="product in products"
        :key="product.id"
        class="sf-product-card"
        :class="`sf-product-card--${config.cardStyle}`"
      >
        <div class="sf-product-card__media">
          <img
            v-if="config.showImage && product.image"
            class="sf-product-card__image"
            :src="product.image"
            :alt="product.name"
            loading="lazy"
            decoding="async"
          >
          <div v-else-if="config.showImage" class="sf-product-card__image sf-product-card__image--empty" aria-hidden="true" />

          <div v-if="config.showBadges" class="sf-product-card__badges">
            <span v-if="discountPercent(product)" class="sf-badge sf-badge--sale">
              -{{ discountPercent(product) }}%
            </span>
            <span v-if="product.is_weighed" class="sf-badge sf-badge--info">por kg</span>
            <span v-if="!product.available_for_delivery" class="sf-badge sf-badge--muted">só retirada</span>
          </div>
        </div>

        <div class="sf-product-card__body">
          <h3 class="sf-product-card__name">{{ product.name }}</h3>

          <p v-if="config.showDescription && product.description" class="sf-product-card__description">
            {{ product.description }}
          </p>

          <div v-if="config.showRating" class="sf-rating" aria-hidden="true">
            <MaterialIcon name="star" :size="14" class="sf-rating__star" />
            <span class="sf-rating__value">{{ product.preparation_minutes ? `${product.preparation_minutes} min` : "Novo" }}</span>
          </div>

          <div class="sf-product-card__foot">
            <div v-if="config.showPrice" class="sf-product-card__price">
              <span>{{ formatPrice(product.current_price) }}</span>
              <span v-if="config.showOldPrice && product.promotional_price" class="sf-product-card__price-was">
                {{ formatPrice(product.price) }}
              </span>
            </div>

            <button
              v-if="config.showButton"
              type="button"
              class="sf-product-card__add"
              :aria-label="`Adicionar ${product.name}`"
            >
              +
            </button>
          </div>
        </div>
      </article>
    </div>

    <p v-else class="sf-empty">Nenhum produto disponível nesta seção.</p>
  </div>
</template>
