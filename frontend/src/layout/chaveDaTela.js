/**
 * A chave da tela no `<component :key>` do layout: mudou, a tela REMONTA.
 *
 * - PDV: a etapa (`step`) e o pedido (`order`) moram na URL para o botão
 *   Voltar, mas trocar de etapa não pode remontar e perder o pedido montado.
 * - Lista (`meta.estadoNaUrl`): página e filtros moram na URL
 *   (`useListUrlState`); com a query na chave, cada letra digitada na busca
 *   remontava a lista inteira.
 * - O resto remonta a cada endereço diferente (`fullPath`).
 *
 * `escopo` é o restaurante ativo e o contador de recarga: trocar remonta tudo.
 */
export const ROTAS_DO_PDV = ["pdv", "pedido-editar-itens"];

export function chaveDaTela(route, escopo) {
  if (ROTAS_DO_PDV.includes(String(route.name))) {
    const { step: _etapa, order: _pedido, ...query } = route.query;
    return `${route.path}:${JSON.stringify(query)}:${escopo}`;
  }
  return `${route.meta?.estadoNaUrl ? route.path : route.fullPath}:${escopo}`;
}
