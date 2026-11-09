/**
 * O estado de uma lista mora na URL: página, ordem, busca e filtros.
 *
 * Voltar de um registro, recarregar a aba ou mandar o link para alguém abre
 * a lista exatamente como estava: `/notas-fiscais?pagina=3&f_status=error`.
 *
 * A tela declara os CAMPOS que espelha — cada um sabe ler o próprio estado
 * como texto e escrever a partir do texto. Um campo com `prefixo` espelha um
 * objeto inteiro (os filtros avançados): `{status: "error"}` vira `f_status=error`.
 *
 * Usa `router.replace`, não `push`: mexer num filtro não cria uma entrada no
 * histórico, então o "Voltar" sai da lista em vez de desfazer filtro por filtro.
 * Parâmetros que a tela não declara (filtros vindos de link) ficam intactos.
 */
import { watch } from "vue";

const vazio = (valor) => valor === "" || valor === null || valor === undefined;

function lerTudo(campos) {
  const query = {};
  for (const campo of campos) {
    if (campo.prefixo) {
      for (const [nome, valor] of Object.entries(campo.ler() || {})) {
        if (!vazio(valor)) query[`${campo.prefixo}${nome}`] = String(valor);
      }
    } else {
      const valor = campo.ler();
      if (!vazio(valor)) query[campo.chave] = String(valor);
    }
  }
  return query;
}

const ehDaTela = (campos, chave) => campos.some((campo) =>
  (campo.prefixo ? chave.startsWith(campo.prefixo) : chave === campo.chave));

export function useListUrlState({ route, router, campos }) {
  const nomeDaRota = route.name;
  let restaurou = false;

  for (const campo of campos) {
    if (campo.prefixo) {
      const valores = Object.fromEntries(Object.entries(route.query)
        .filter(([chave]) => chave.startsWith(campo.prefixo))
        .map(([chave, valor]) => [chave.slice(campo.prefixo.length), valor]));
      if (Object.keys(valores).length) {
        campo.escrever(valores);
        restaurou = true;
      }
    } else if (!vazio(route.query[campo.chave])) {
      campo.escrever(String(route.query[campo.chave]));
      restaurou = true;
    }
  }

  watch(() => lerTudo(campos), (daTela) => {
    // `route` já aponta para o destino enquanto a tela ainda existe: sem isto,
    // sair da lista gravaria os filtros dela no endereço do registro aberto.
    if (route.name !== nomeDaRota) return;
    const outros = Object.fromEntries(Object.entries(route.query).filter(([chave]) => !ehDaTela(campos, chave)));
    const query = { ...outros, ...daTela };
    if (JSON.stringify(query) === JSON.stringify(route.query)) return;
    router.replace({ query });
  }, { deep: true });

  return { restaurou };
}
