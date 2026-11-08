import { api } from "../services/api";
import { normalizeApiError } from "./apiError";

/**
 * Baixa um arquivo da API e o entrega ao navegador com o nome `nome`.
 *
 * Passa pelo `api` (e não por um link direto) para levar o cookie de sessão e
 * para o erro virar mensagem na tela em vez de uma aba com JSON. Sem limite de
 * tempo: um ZIP de um mês inteiro passa fácil dos 15 s padrão do cliente.
 */
export async function baixarArquivo(url, nome) {
  let resposta;
  try {
    resposta = await api.get(url, { responseType: "blob", timeout: 0, skipRestaurantScope: true });
  } catch (erro) {
    throw await erroLegivel(erro);
  }
  const endereco = URL.createObjectURL(resposta.data);
  const link = document.createElement("a");
  link.href = endereco;
  link.download = nome;
  link.click();
  URL.revokeObjectURL(endereco);
}

/** Com `responseType: "blob"` o corpo do erro também chega como Blob. */
export async function erroLegivel(erro) {
  const corpo = erro?.response?.data;
  if (corpo instanceof Blob) {
    try {
      erro.response.data = JSON.parse(await corpo.text());
    } catch {
      // Corpo que não é JSON: fica a mensagem padrão do status.
    }
  }
  return normalizeApiError(erro);
}
