/**
 * Estado de filtro/ordenação compartilhado entre a barra de filtros e a vitrine.
 *
 * Os dois são blocos independentes no editor: o cliente pode remover a barra,
 * colocar duas vitrines na mesma página ou nenhuma barra. Por isso o estado
 * mora no renderer (`provide`) e não dentro de um dos blocos — e por isso o
 * `inject` tem fallback: uma vitrine sem barra nenhuma continua funcionando,
 * usando a configuração salva no próprio bloco.
 */
import type { Ref } from 'vue'
import { STOREFRONT_FILTER_KEY } from '~~/lib/builder/registry/injection'

export interface StorefrontFilterState {
  categoryId: Ref<string>
  sort: Ref<string>
  setCategory: (value: string) => void
  setSort: (value: string) => void
}

function createFilterState(): StorefrontFilterState {
  const categoryId = ref('')
  const sort = ref('default')
  return {
    categoryId,
    sort,
    setCategory: (value: string) => {
      // Clicar de novo na categoria ativa limpa o filtro — é o gesto que o
      // usuário tenta quando quer "ver tudo" sem procurar o botão certo.
      categoryId.value = categoryId.value === value ? '' : value
    },
    setSort: (value: string) => {
      sort.value = value || 'default'
    },
  }
}

/** Chamado uma vez pelo renderer da página. */
export function provideStorefrontFilter(): StorefrontFilterState {
  const state = createFilterState()
  provide(STOREFRONT_FILTER_KEY, state)
  return state
}

/** Chamado pelos blocos. Sem renderer por perto, devolve um estado próprio. */
export function useStorefrontFilter(): StorefrontFilterState {
  return inject(STOREFRONT_FILTER_KEY, null) ?? createFilterState()
}
