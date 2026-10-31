const REMOTE_TYPES = new Set(["remote-dropdown", "remote-multiselect"]);

function requestKey(field) {
  return JSON.stringify([field.endpoint, Boolean(field.globalScope)]);
}

function mapRows(rows, field) {
  return rows.map((row) => ({
    label: String(row[field.optionLabel ?? "name"] ?? row.id),
    value: row[field.optionValue ?? "id"],
    group: row[field.optionGroup ?? "group"] ?? "",
    description: String(row.description ?? ""),
  }));
}

/** Busca cada endpoint/escopo uma vez e adapta o resultado para cada campo. */
export async function loadRemoteOptions(fields, get) {
  const groups = new Map();
  for (const field of fields) {
    if (!REMOTE_TYPES.has(field.type) || !field.endpoint) continue;
    const key = requestKey(field);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(field);
  }

  const options = {};
  await Promise.all([...groups.values()].map(async (group) => {
    const sample = group[0];
    try {
      const response = await get(sample.endpoint, {
        params: { page_size: 200 },
        skipRestaurantScope: Boolean(sample.globalScope),
      });
      const rows = response.data.results || response.data || [];
      for (const field of group) options[field.name] = mapRows(rows, field);
    } catch {
      for (const field of group) options[field.name] = [];
    }
  }));
  return options;
}
