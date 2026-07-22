/**
 * Normalização de erros da API (Sprint 1 · STC-014).
 *
 * Converte qualquer erro do axios/DRF em uma forma previsível para a UI,
 * distinguindo os status 400/401/403/404/409/422/500 e separando os erros
 * por campo da mensagem geral. Elimina os "erros silenciosos": sempre há uma
 * mensagem compreensível para o usuário e, em dev, um log técnico útil.
 *
 * @typedef {object} NormalizedError
 * @property {number|null} status         Status HTTP (null se falha de rede).
 * @property {string} code                Código do erro (do backend ou derivado).
 * @property {string} message             Mensagem geral para o usuário.
 * @property {Record<string,string>} fieldErrors  Erros por campo ({ campo: msg }).
 * @property {boolean} isNetwork          True quando não houve resposta do servidor.
 * @property {boolean} isValidation       True para 400/422 com erros de campo.
 */

const STATUS_MESSAGES = {
  400: "Verifique os dados informados.",
  401: "Sua sessão expirou. Entre novamente.",
  403: "Você não tem permissão para esta ação.",
  404: "Registro não encontrado.",
  409: "Conflito: este registro já existe ou está em uso.",
  422: "Verifique os dados informados.",
  429: "Muitas tentativas. Aguarde um instante e tente novamente.",
  500: "Erro interno do servidor. Tente novamente em instantes.",
  502: "Servidor indisponível no momento. Tente novamente.",
  503: "Servidor indisponível no momento. Tente novamente.",
};

/** Achata um valor de erro do DRF (string, lista, ou aninhado) em texto. */
function flatten(value) {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(flatten).filter(Boolean).join(" ");
  if (typeof value === "object") return Object.values(value).map(flatten).filter(Boolean).join(" ");
  return String(value);
}

/**
 * @param {unknown} err  Erro capturado (idealmente um AxiosError).
 * @returns {NormalizedError}
 */
export function normalizeApiError(err) {
  const response = err?.response;
  const status = response?.status ?? null;

  // Falha de rede / sem resposta (servidor fora, CORS, timeout).
  if (!response) {
    logTechnical(err, { status: null, network: true });
    return {
      status: null,
      code: "network_error",
      message: "Sem conexão com o servidor. Verifique sua internet e tente novamente.",
      fieldErrors: {},
      isNetwork: true,
      isValidation: false,
    };
  }

  // O backend envelopa erros em { success, status_code, error: { code, message } }.
  const body = response.data;
  const envelope = body?.error;
  const detail = envelope?.message ?? body;
  const code = envelope?.code || derivedCode(status);

  const fieldErrors = {};
  let generalMessage = "";

  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    for (const [key, value] of Object.entries(detail)) {
      const message = flatten(value);
      if (key === "detail" || key === "non_field_errors") generalMessage = message;
      else fieldErrors[key] = message;
    }
  } else if (detail) {
    generalMessage = flatten(detail);
  }

  const hasFieldErrors = Object.keys(fieldErrors).length > 0;
  if (!generalMessage) {
    generalMessage = hasFieldErrors
      ? "Corrija os campos destacados e tente novamente."
      : STATUS_MESSAGES[status] || "Não foi possível concluir a operação.";
  }

  logTechnical(err, { status, code });

  return {
    status,
    code,
    message: generalMessage,
    fieldErrors,
    isNetwork: false,
    isValidation: (status === 400 || status === 422) && hasFieldErrors,
  };
}

function derivedCode(status) {
  return (
    {
      400: "bad_request",
      401: "not_authenticated",
      403: "permission_denied",
      404: "not_found",
      409: "conflict",
      422: "unprocessable",
      500: "server_error",
    }[status] || "error"
  );
}

/** Log técnico só em desenvolvimento — nada de ruído no console de produção. */
function logTechnical(err, meta) {
  if (!import.meta.env.DEV) return;
  window.console.warn("[api-error]", meta, err?.response?.data ?? err?.message ?? err);
}
