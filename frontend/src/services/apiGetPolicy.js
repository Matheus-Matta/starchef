import { createGetWithCache } from "./apiGetCache";
import { getBrowserValue } from "./browserPersistence";

const LOOKUP_CACHE_TTL_MS = 60_000;
const LOOKUP_ENDPOINTS = new Set([
  "/restaurants/",
  "/menu/categories/",
  "/menu/addons/",
  "/tables/sectors/",
  "/payments/methods/",
  "/stock/locations/",
  "/stock/suppliers/",
  "/stock/label-templates/",
  "/stock/settings/current/",
]);

/** Instala deduplicação geral e cache curto somente para catálogos seguros. */
export function installGetPolicy(api) {
  const cachedGet = createGetWithCache(
    api.get.bind(api),
    () => getBrowserValue("starchef-restaurant-scope") || "todos",
  );
  api.get = (url, config = {}) => cachedGet(url, {
    cacheTtlMs: LOOKUP_ENDPOINTS.has(url) ? LOOKUP_CACHE_TTL_MS : 0,
    ...config,
  });
  api.get.clearCache = cachedGet.clearCache;
}
