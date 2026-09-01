const FIELD_MESSAGES = {
  restaurant: "Selecione o restaurante desta entrada.",
  location: "Selecione o armazém que receberá os produtos.",
  effective_date: "Informe a data da entrada.",
  ingredient: "Selecione o insumo recebido.",
  package_quantity: "Informe quantas embalagens foram recebidas.",
  content_per_package: "Informe quanto há em cada embalagem, por exemplo: 1 para um pacote de 1 kg.",
  content_unit: "Selecione a unidade do conteúdo da embalagem.",
  manufactured_at: "Informe uma data de fabricação válida.",
  expires_at: "Informe a data de validade deste insumo.",
  label_count: "Informe uma quantidade de etiquetas entre 1 e 99.",
};

function messageText(value) {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(messageText).filter(Boolean).join(" ");
  if (typeof value === "object") return Object.values(value).map(messageText).filter(Boolean).join(" ");
  return String(value);
}

function friendlyMessage(field, value) {
  const message = messageText(value);
  if (!message) return FIELD_MESSAGES[field] || "Verifique este campo.";
  if (/não pode ser nulo|may not be null|obrigatório|required/i.test(message)) {
    return FIELD_MESSAGES[field] || message;
  }
  return message;
}

function rowKey(row, index) {
  return String(row?._key ?? index);
}

function asDateNumber(value) {
  const parsed = value instanceof Date ? value : parseApiDate(value);
  if (!(parsed instanceof Date) || Number.isNaN(parsed.getTime())) return null;
  return parsed.getFullYear() * 10_000 + (parsed.getMonth() + 1) * 100 + parsed.getDate();
}

export function parseApiDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

export function toApiDate(value) {
  if (!value) return null;
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return null;
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function validateStockEntry({ form, rows, expiryRequired = false, forPosting = false }) {
  const formErrors = {};
  const rowErrors = {};
  let firstError = "";

  const addFormError = (field, message = FIELD_MESSAGES[field]) => {
    formErrors[field] = message;
    if (!firstError) firstError = message;
  };
  const addRowError = (row, index, field, message = FIELD_MESSAGES[field]) => {
    const key = rowKey(row, index);
    rowErrors[key] ||= {};
    rowErrors[key][field] = message;
    if (!firstError) firstError = `Linha ${index + 1}: ${message}`;
  };

  if (!form.restaurant) addFormError("restaurant");
  if (!form.location) addFormError("location");
  if (!toApiDate(form.effective_date)) addFormError("effective_date");
  if (forPosting && rows.length === 0) {
    addFormError("items", "Adicione ao menos um insumo antes de confirmar a entrada.");
  }

  rows.forEach((row, index) => {
    if (!row.ingredient) addRowError(row, index, "ingredient");

    const packages = Number(row.package_quantity);
    if (row.package_quantity == null || !Number.isFinite(packages) || packages <= 0) {
      addRowError(row, index, "package_quantity");
    }

    const content = Number(row.content_per_package);
    if (row.content_per_package == null || !Number.isFinite(content) || content <= 0) {
      addRowError(row, index, "content_per_package");
    }
    if (!row.content_unit) addRowError(row, index, "content_unit");

    const manufactured = asDateNumber(row.manufactured_at);
    const expires = asDateNumber(row.expires_at);
    const effective = asDateNumber(form.effective_date);
    if (row.manufactured_at && manufactured === null) addRowError(row, index, "manufactured_at");
    if (row.expires_at && expires === null) addRowError(row, index, "expires_at");
    if (forPosting && expiryRequired && !expires) addRowError(row, index, "expires_at");
    if (manufactured && expires && manufactured > expires) {
      addRowError(row, index, "expires_at", "A validade deve ser posterior à data de fabricação.");
    } else if (effective && expires && expires < effective) {
      addRowError(row, index, "expires_at", "A validade não pode ser anterior à data da entrada.");
    }

    const labels = Number(row.label_count);
    if (!Number.isInteger(labels) || labels < 1 || labels > 99) addRowError(row, index, "label_count");
  });

  const valid = Object.keys(formErrors).length === 0 && Object.keys(rowErrors).length === 0;
  return {
    valid,
    formErrors,
    rowErrors,
    message: valid ? "" : `Corrija os campos destacados. ${firstError}`,
  };
}

export function stockEntryApiErrors(error, rows = []) {
  const body = error?.response?.data;
  const detail = body?.error?.message ?? body;
  const formErrors = {};
  const rowErrors = {};
  let firstError = "";

  if (!detail || typeof detail !== "object" || Array.isArray(detail)) {
    return { formErrors, rowErrors, message: messageText(detail), hasFieldErrors: false };
  }

  for (const field of ["restaurant", "location", "effective_date", "document_number", "notes"]) {
    if (detail[field] == null) continue;
    formErrors[field] = friendlyMessage(field, detail[field]);
    if (!firstError) firstError = formErrors[field];
  }

  const itemErrors = Array.isArray(detail.items) ? detail.items : [];
  itemErrors.forEach((errors, index) => {
    if (!errors || typeof errors !== "object" || Array.isArray(errors)) return;
    const key = rowKey(rows[index], index);
    for (const [field, value] of Object.entries(errors)) {
      rowErrors[key] ||= {};
      rowErrors[key][field] = friendlyMessage(field, value);
      if (!firstError) firstError = `Linha ${index + 1}: ${rowErrors[key][field]}`;
    }
  });

  const hasFieldErrors = Object.keys(formErrors).length > 0 || Object.keys(rowErrors).length > 0;
  return {
    formErrors,
    rowErrors,
    message: hasFieldErrors ? `Corrija os campos destacados. ${firstError}` : messageText(detail.detail),
    hasFieldErrors,
  };
}
