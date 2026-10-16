// As linhas que a comanda da pesagem (Balança Rápida) imprime para marcar à
// mão: produto do cardápio, título livre ou linha em branco. O formato é o de
// `Restaurant.linhas_da_comanda` (backend/apps/restaurants/linhas_da_comanda.py);
// o texto do papel é montado no backend (apps/printers/comanda_da_pesagem.py).

/** Os tetos do backend: 20 linhas, título de 1 a 40 caracteres. */
export const MAXIMO_DE_LINHAS = 20;
export const MAXIMO_DO_TITULO = 40;

/** As em branco saem SEMPRE no fim do papel; a tela mostra igual. */
export function emOrdemDeImpressao(linhas) {
  return [...linhas.filter((l) => l.tipo !== "branco"), ...linhas.filter((l) => l.tipo === "branco")];
}

/** Da API para a tela; tipo desconhecido é descartado. */
export function linhasDaApi(bruto) {
  const linhas = (Array.isArray(bruto) ? bruto : []).flatMap((linha) => {
    if (linha?.tipo === "branco") return [{ tipo: "branco" }];
    if (linha?.tipo === "texto" && String(linha.nome || "").trim()) return [{ tipo: "texto", nome: String(linha.nome).trim() }];
    if (linha?.tipo === "produto" && linha.produto) return [{ tipo: "produto", produto: String(linha.produto) }];
    return [];
  });
  return emOrdemDeImpressao(linhas);
}

/** O que aparece na linha: o nome do produto, o título ou nada (em branco). */
export function rotuloDaLinha(linha, nomesDosProdutos) {
  if (linha.tipo === "texto") return linha.nome;
  if (linha.tipo === "produto") return nomesDosProdutos[linha.produto] || "Produto fora do cardápio (não sai)";
  return "";
}

/** Título digitado, sem espaços sobrando; vazio ou longo demais vira `null`. */
export function tituloValido(texto) {
  const nome = String(texto || "").split(/\s+/).join(" ").trim();
  return nome && nome.length <= MAXIMO_DO_TITULO ? nome : null;
}

/** Troca a linha `de` com a vizinha; linha em branco não sai do fim. */
export function mover(linhas, de, para) {
  const copia = [...linhas];
  if (para < 0 || para >= copia.length || copia[de]?.tipo === "branco" || copia[para]?.tipo === "branco") return copia;
  copia.splice(para, 0, copia.splice(de, 1)[0]);
  return copia;
}
