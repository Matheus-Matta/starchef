<script setup lang="ts">
/**
 * Terceiro nível do cabeçalho: a barra branca compacta de navegação.
 *
 * Dois grupos em extremos opostos — à esquerda o que o visitante veio fazer
 * (produtos, novidades, entrega), à direita o apoio (trocas, dúvidas, contato).
 * O `space-between` é o que separa os dois sem precisar de divisória: distância
 * já diz que são coisas diferentes.
 *
 * A fonte é deliberadamente pequena (10-11px, peso 500). Esta barra é o nível
 * MENOS importante dos três; se tivesse o mesmo peso da busca, o cabeçalho
 * viraria três faixas competindo entre si.
 *
 * Nenhum rótulo é escrito aqui. Os itens vêm dos menus resolvidos pelo backend
 * (`menus[handle]`), então o restaurante monta a lista uma vez no cadastro de
 * menus e ela aparece aqui — inclusive os submenus, que viram dropdown.
 */
import type { StorefrontMenu, StorefrontMenuEntry } from '~~/types/storefront'

const props = defineProps<{
  /** Handle do menu da esquerda (`nav_menu` do site). */
  primary?: string
  /** Handle do menu da direita (`secondary_menu`). */
  secondary?: string
}>()

const storefront = useStorefrontData()
const link = useSiteLink()

function entriesOf(handle?: string): StorefrontMenuEntry[] {
  if (!handle) return []
  const menu: StorefrontMenu | undefined = storefront.value.menus?.[handle]
  return menu?.items ?? []
}

const left = computed(() => entriesOf(props.primary))
const right = computed(() => entriesOf(props.secondary))

// Sem nenhum dos dois lados a barra some por inteiro. Uma faixa branca de 38px
// sem conteúdo apenas empurraria a capa para baixo.
const hasContent = computed(() => left.value.length > 0 || right.value.length > 0)

function hrefOf(entry: StorefrontMenuEntry): string {
  // As URLs dos itens vêm do backend relativas à RAIZ DO SITE (`/categoria/x`).
  // Sem o prefixo do slug elas cairiam na raiz do servidor.
  return link(entry.url) || '#'
}
</script>

<template>
  <nav v-if="hasContent" class="sf-nav" aria-label="Navegação do site">
    <div class="sf-nav__inner">
      <ul class="sf-nav__group">
        <li v-for="entry in left" :key="entry.id" class="sf-nav__item">
          <a
            class="sf-nav__link"
            :href="hrefOf(entry)"
            :target="entry.opens_in_new_tab ? '_blank' : undefined"
            :rel="entry.opens_in_new_tab ? 'noopener' : undefined"
          >
            {{ entry.title }}
            <MaterialIcon v-if="entry.children.length" name="expand_more" :size="10" class="sf-nav__chevron" />
          </a>

          <!-- O submenu abre no hover e no foco: só hover deixaria a lista
               inalcançável por teclado. -->
          <ul v-if="entry.children.length" class="sf-nav__dropdown">
            <li v-for="child in entry.children" :key="child.id">
              <a
                :href="hrefOf(child)"
                :target="child.opens_in_new_tab ? '_blank' : undefined"
                :rel="child.opens_in_new_tab ? 'noopener' : undefined"
              >
                {{ child.title }}
              </a>
            </li>
          </ul>
        </li>
      </ul>

      <ul class="sf-nav__group sf-nav__group--end">
        <li v-for="entry in right" :key="entry.id" class="sf-nav__item">
          <a
            class="sf-nav__link"
            :href="hrefOf(entry)"
            :target="entry.opens_in_new_tab ? '_blank' : undefined"
            :rel="entry.opens_in_new_tab ? 'noopener' : undefined"
          >
            {{ entry.title }}
          </a>
        </li>
      </ul>
    </div>
  </nav>
</template>
