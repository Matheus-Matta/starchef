function appendValue(payload, field, value) {
  if (value === null || value === undefined) return;
  payload.append(field, String(value));
}

export function buildFiscalConfigPayload({
  form,
  editableFields,
  secretFields,
  certificateFile,
}) {
  const values = {};
  for (const field of editableFields) values[field] = form[field];
  for (const field of secretFields) {
    if (form[field]) values[field] = form[field];
  }

  values.series = Number(form.series) || 1;
  values.uf = (form.uf || "").toUpperCase();
  if (!certificateFile) return values;

  const payload = new FormData();
  for (const [field, value] of Object.entries(values)) appendValue(payload, field, value);
  payload.append("certificate_file", certificateFile);
  return payload;
}
