export function createBulkForm(scopedRestaurantId = null) {
  return {
    restaurant_id: scopedRestaurantId || null,
    sector_id: null,
    from_number: null,
    to_number: null,
  };
}

export function missingBulkScope(type, form) {
  if (!form.restaurant_id) return "restaurant";
  if (type === "tables" && !form.sector_id) return "sector";
  return null;
}

export function buildBulkPayload(type, form) {
  const payload = {
    restaurant: form.restaurant_id,
    to_number: form.to_number,
  };
  if (type === "tables") payload.sector = form.sector_id;
  if (form.from_number) payload.from_number = form.from_number;
  return payload;
}
