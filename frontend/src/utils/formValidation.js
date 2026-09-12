import { isValidCpf } from "./cpf";

/**
 * Validacao do formulario ANTES de ir ao servidor.
 *
 * Espelha as regras que o backend aplica em todo recurso (obrigatorio, numero
 * inteiro, nao-negativo, tamanho maximo, CPF/CNPJ, campo menor-ou-igual a outro)
 * para que o operador veja o erro no campo, na hora — e nao depois de um
 * round-trip que devolve "Um numero inteiro valido e exigido" num toast.
 *
 * As regras sao declaradas em `formFields` (config/resources.js):
 *   - `required: true`
 *   - `type: "number"`  → inteiro; `type: "decimal"` → numero
 *   - `min` (padrao 0; `allowNegative: true` libera valor assinado)
 *   - `maxlength`
 *   - `document: "cpf" | "cnpj"`
 *   - `notGreaterThan: { field, message }`  → regra cruzada (ex.: SLA)
 *
 * O teste de carga (loadtest/) mostrou exatamente estes 400 saindo dos forms.
 */

export const MESSAGES = {
  required: "Este campo é obrigatório.",
  integer: "Informe um número inteiro.",
  number: "Informe um número válido.",
  negative: "Não pode ser negativo.",
  min: (min) => `Não pode ser menor que ${min}.`,
  maxlength: (max) => `Máximo de ${max} caracteres.`,
  cpf: "CPF inválido.",
  cnpj: "Informe um CNPJ com 14 dígitos.",
};

const INTEGER_RE = /^-?\d+$/;

function isEmpty(value) {
  if (value === "" || value === null || value === undefined) return true;
  return Array.isArray(value) && value.length === 0;
}

function digitsOf(value) {
  return String(value || "").replace(/\D/g, "");
}

/** Piso do campo: `min` declarado; senao 0, a menos que ele seja assinado. */
function minimumOf(field) {
  if (field.min !== undefined && field.min !== null) return Number(field.min);
  return field.allowNegative ? null : 0;
}

function numericError(field, value) {
  const text = String(value).trim();
  if (field.type === "number" && !INTEGER_RE.test(text)) return MESSAGES.integer;
  const parsed = Number(text);
  if (!Number.isFinite(parsed)) return MESSAGES.number;
  const min = minimumOf(field);
  if (min !== null && parsed < min) return min === 0 ? MESSAGES.negative : MESSAGES.min(min);
  return "";
}

function documentError(field, value) {
  if (field.document === "cpf" && !isValidCpf(value)) return MESSAGES.cpf;
  if (field.document === "cnpj" && digitsOf(value).length !== 14) return MESSAGES.cnpj;
  return "";
}

/** Regra cruzada: este campo nao pode passar do outro (ambos preenchidos). */
function crossFieldError(field, value, formData) {
  const rule = field.notGreaterThan;
  if (!rule) return "";
  const other = formData[rule.field];
  if (isEmpty(other) || isEmpty(value)) return "";
  const mine = Number(value);
  const theirs = Number(other);
  if (!Number.isFinite(mine) || !Number.isFinite(theirs)) return "";
  return mine > theirs ? rule.message : "";
}

/** Mensagem de erro de UM campo, ou "" quando ele esta valido. */
export function validateField(field, value, formData = {}) {
  if (field.header) return "";
  if (isEmpty(value)) return field.required && field.type !== "file" ? MESSAGES.required : "";
  if (field.type === "number" || field.type === "decimal") {
    const error = numericError(field, value);
    if (error) return error;
  }
  if (field.maxlength && String(value).length > field.maxlength) {
    return MESSAGES.maxlength(field.maxlength);
  }
  return documentError(field, value) || crossFieldError(field, value, formData);
}

/**
 * Valida todos os campos. Devolve `{ nome: mensagem }` so com os que falharam —
 * objeto vazio significa que pode enviar.
 */
export function validateForm(formFields, formData) {
  const errors = {};
  for (const field of formFields) {
    const error = validateField(field, formData[field.name], formData);
    if (error) errors[field.name] = error;
  }
  return errors;
}
