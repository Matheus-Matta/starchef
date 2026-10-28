export const STOCK_ITEM_TYPES = [
  { label: "Insumos", value: "ingredient", kind: "ingredient", endpoint: "/menu/ingredients/" },
  { label: "Produtos", value: "product", kind: "product", endpoint: "/menu/products/" },
  { label: "Mercadorias para revenda", value: "RESALE_PRODUCT", kind: "product", endpoint: "/menu/products/", itemType: "RESALE_PRODUCT" },
  { label: "Materiais de consumo", value: "CONSUMABLE", kind: "product", endpoint: "/menu/products/", itemType: "CONSUMABLE" },
  { label: "Reutilizáveis", value: "REUSABLE_MATERIAL", kind: "product", endpoint: "/menu/products/", itemType: "REUSABLE_MATERIAL" },
  { label: "Equipamentos", value: "EQUIPMENT", kind: "product", endpoint: "/menu/products/", itemType: "EQUIPMENT" },
  { label: "Ativos fixos", value: "FIXED_ASSET", kind: "product", endpoint: "/menu/products/", itemType: "FIXED_ASSET" },
  { label: "Embalagens", value: "PACKAGING", kind: "product", endpoint: "/menu/products/", itemType: "PACKAGING" },
  { label: "Outros itens", value: "OTHER", kind: "product", endpoint: "/menu/products/", itemType: "OTHER" },
];

export function stockItemType(value) {
  return STOCK_ITEM_TYPES.find((item) => item.value === value) || STOCK_ITEM_TYPES[0];
}
