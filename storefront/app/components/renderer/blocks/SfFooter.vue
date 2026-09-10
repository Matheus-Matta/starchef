<script setup lang="ts">
/**
 * Rodapé: identificação do restaurante, colunas de links e formas de pagamento.
 *
 * As colunas de links NÃO são texto fixo — cada uma aponta para um `menu.Menu`
 * pelo slug, o mesmo mecanismo do cabeçalho (`nav_menu`/`secondary_menu`). É o
 * que permite ao restaurante criar "Política de privacidade", "Termos de uso"
 * ou "Contato" depois, como um menu manual com links personalizados, sem
 * precisar mexer em código: basta apontar a coluna para o slug do menu novo.
 */
import type { RenderNode } from '~~/types/builder'
import { propBool, resolveFooterColumns } from '~~/lib/storefront/resolve'

const props = defineProps<{ node: RenderNode; nodeClass: (string | undefined)[] }>()

const storefront = useStorefrontData()
const link = useSiteLink()

const showPayments = computed(() => propBool(props.node.props, 'show_payment_methods', true))
const brand = computed(() => storefront.value.site.name || storefront.value.restaurant.name)
const address = computed(() => {
  const parts = storefront.value.restaurant.address
  return [parts.street, parts.district, parts.city].filter(Boolean).join(', ')
})
const year = new Date().getFullYear()

// Mesma regra do canvas do editor: ver `lib/storefront/resolve`.
const columns = computed(() => resolveFooterColumns(storefront.value, props.node.props))
</script>

<template>
  <footer :class="nodeClass">
    <div class="sf-footer__inner">
      <div class="sf-footer__col">
        <strong>{{ brand }}</strong>
        <p v-if="address" style="margin-top: 6px; opacity: 0.8">{{ address }}</p>
        <p style="margin-top: 6px; opacity: 0.6; font-size: 13px">© {{ year }}</p>
      </div>

      <div v-for="column in columns" :key="column.title" class="sf-footer__col">
        <p class="sf-footer__col-title">{{ column.title }}</p>
        <ul class="sf-footer__links">
          <li v-for="item in column.items" :key="item.id">
            <a :href="link(item.url) || '#'" :target="item.opens_in_new_tab ? '_blank' : undefined" :rel="item.opens_in_new_tab ? 'noopener' : undefined">
              {{ item.title }}
            </a>
          </li>
        </ul>
      </div>

      <div v-if="showPayments && storefront.payment_methods.length" class="sf-footer__col">
        <p class="sf-footer__col-title">Formas de pagamento</p>
        <div style="display: flex; flex-wrap: wrap; gap: 8px">
          <span v-for="method in storefront.payment_methods" :key="method.id" class="sf-badge">
            {{ method.name }}
          </span>
        </div>
      </div>
    </div>

    <SfNode v-for="child in node.children" :key="child.id" :node="child" />
  </footer>
</template>
