import { api } from "../services/api";
import { normalizeApiError } from "../utils/apiError";

/**
 * "Remover vínculo" de um item da NF-e de entrada.
 *
 * Existe porque vincular o produto errado (ou cadastrar como patrimônio o que
 * era produto) não tinha volta: o lápis só trocava por outro, e o aprendizado
 * do fornecedor continuava apontando para o vínculo errado — a próxima nota
 * dele chegava vinculada errado de novo, sozinha. O backend apaga os dois.
 */
export function useInboundItemUnlink({ confirm, toast }) {
  function unlinkInboundItem(item, { onDone } = {}) {
    if (!item?.id) return;
    const alvo = item.product_name || item.ingredient_name || "o cadastro atual";
    confirm.require({
      header: "Remover vínculo",
      message:
        `O item "${item.description}" deixa de apontar para ${alvo}. ` +
        "O sistema também esquece esse vínculo para as próximas notas deste fornecedor. " +
        "Depois é só vincular de novo ao item certo.",
      icon: "pi pi-link",
      acceptLabel: "Remover vínculo",
      rejectLabel: "Cancelar",
      acceptClass: "p-button-danger",
      accept: async () => {
        try {
          const { data } = await api.post(`/inbound-nfe-items/${item.id}/unlink/`);
          toast.add({
            severity: "info",
            summary: "Vínculo removido",
            detail: data?.message || "O item pode ser vinculado de novo.",
            life: 4000,
          });
          await onDone?.(data);
        } catch (err) {
          toast.add({
            severity: "error",
            summary: "Não foi possível remover o vínculo",
            detail: normalizeApiError(err).message,
            life: 5000,
          });
        }
      },
    });
  }

  return { unlinkInboundItem };
}
