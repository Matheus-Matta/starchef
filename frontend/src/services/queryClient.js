/**
 * Cache das leituras da API (TanStack Query), um só para o app inteiro.
 *
 * O que ele resolve: voltar de um registro para a lista baixava a lista de
 * novo, sempre, e a tela esperava a rede para mostrar o que já tinha mostrado
 * segundos antes. Com o cache, a lista aparece NA HORA e uma única requisição
 * confere por baixo se algo mudou (stale-while-revalidate).
 *
 * Toda chave começa por `[tipo, endpoint, escopo]`. O escopo é o restaurante
 * ativo: um restaurante nunca mostra o cache do outro.
 */
import { QueryClient } from "@tanstack/vue-query";

import { getBrowserValue } from "./browserPersistence";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Abaixo disto, voltar para a tela nem pergunta ao servidor.
      staleTime: 10_000,
      // Lista que ninguém abriu há 5 minutos sai da memória.
      gcTime: 5 * 60_000,
      // O tempo real (WebSocket) já atualiza as listas abertas.
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
});

export function currentScope() {
  return getBrowserValue("starchef-restaurant-scope") || "todos";
}

/** O assunto de um endereço: "/invoices/bulk-resend/" → "invoices". */
export function assuntoDe(url = "") {
  const caminho = String(url).split("?")[0].replace(/^https?:\/\/[^/]+/, "").replace(/^\/api\/v\d+/, "");
  return caminho.split("/").filter(Boolean)[0] || "";
}

/**
 * Uma escrita deixa velho só o cache do PRÓPRIO assunto: reenviar nota não
 * joga fora a lista de produtos. O cache de GET antigo limpava tudo.
 */
export function invalidarAssunto(url) {
  const assunto = assuntoDe(url);
  if (!assunto) return Promise.resolve();
  return queryClient.invalidateQueries({ predicate: (query) => assuntoDe(query.queryKey[1]) === assunto });
}
