/**
 * Aba aberta numa versão antiga do painel: recarrega uma vez e segue.
 *
 * Cada deploy gera arquivos com nomes novos (`HomeView-<hash>.js`) e apaga os
 * antigos. A aba que estava aberta antes continua rodando o código velho e,
 * ao abrir uma tela pela primeira vez (PDV, Pedidos), pede um arquivo que não
 * existe mais: "Failed to fetch dynamically imported module". Recarregar
 * baixa o index.html novo, que aponta para os arquivos novos.
 *
 * UMA vez: se o erro voltar logo depois do recarregamento, o problema é
 * outro (servidor fora, rede caindo) e recarregar em laço só piora — aí o
 * erro segue para a tela, como antes.
 */
const CHAVE = "starchef:recarregou-por-versao";
const JANELA_MS = 30_000;

const PADROES = [
  /Failed to fetch dynamically imported module/i,
  /error loading dynamically imported module/i,
  /Importing a module script failed/i,
  /Unable to preload CSS/i,
];

export function isStaleChunkError(error) {
  const texto = String(error?.message ?? error ?? "");
  return PADROES.some((padrao) => padrao.test(texto));
}

function lerMarca(storage) {
  try {
    return Number(storage.getItem(CHAVE)) || 0;
  } catch {
    return 0;
  }
}

/** Recarrega (devolve true) ou desiste porque já recarregou há pouco. */
export function reloadOnce(destino, { storage = window.sessionStorage, location = window.location, now = Date.now() } = {}) {
  const marca = lerMarca(storage);
  if (marca && now - marca < JANELA_MS) return false;
  try {
    storage.setItem(CHAVE, String(now));
  } catch {
    // Sem sessionStorage (aba anônima restrita): recarrega mesmo assim; o
    // pior caso é um segundo recarregamento, não um laço — o navegador zera
    // a página e o erro, se persistir, aparece na tela.
  }
  location.assign(destino || location.href);
  return true;
}

export function installStaleChunkReload(router) {
  // O Vite dispara este evento quando o pré-carregamento de um pedaço falha.
  window.addEventListener("vite:preloadError", (event) => {
    if (reloadOnce()) event.preventDefault();
  });
  // E o roteador recebe o erro quando a tela é importada sob demanda.
  router.onError((error, to) => {
    if (isStaleChunkError(error)) reloadOnce(to?.fullPath);
  });
}
