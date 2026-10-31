function stable(value) {
  if (value instanceof URLSearchParams) return value.toString();
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
}

function requestKey(url, config, scopeKey) {
  return JSON.stringify(stable({
    url,
    params: config.params || {},
    responseType: config.responseType || "json",
    skipRestaurantScope: Boolean(config.skipRestaurantScope),
    scope: scopeKey(),
  }));
}

/** Deduplica GETs simultâneos e mantém somente caches explicitamente autorizados. */
export function createGetWithCache(rawGet, scopeKey = () => "") {
  const pending = new Map();
  const cached = new Map();
  let generation = 0;

  const get = (url, config = {}) => {
    const { cacheTtlMs = 0, forceRefresh = false, ...requestConfig } = config;
    if (requestConfig.signal || requestConfig.onDownloadProgress) return rawGet(url, requestConfig);

    const key = requestKey(url, requestConfig, scopeKey);
    const saved = cached.get(key);
    if (!forceRefresh && saved?.expiresAt > Date.now()) return Promise.resolve(saved.response);
    if (pending.has(key)) return pending.get(key);

    const requestGeneration = generation;
    const request = rawGet(url, requestConfig)
      .then((response) => {
        if (cacheTtlMs > 0 && requestGeneration === generation) {
          cached.set(key, { response, expiresAt: Date.now() + cacheTtlMs });
        }
        return response;
      })
      .finally(() => {
        if (pending.get(key) === request) pending.delete(key);
      });
    pending.set(key, request);
    return request;
  };

  get.clearCache = () => {
    generation += 1;
    pending.clear();
    cached.clear();
  };
  return get;
}
