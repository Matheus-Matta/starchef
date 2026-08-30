"""Consulta assistida de classificacao de produtos na API Bluesoft Cosmos."""

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, replace

import requests
from django.core.cache import cache

from apps.accounts.models import CosmosConfig

COSMOS_API_URL = "https://api.cosmos.bluesoft.com.br"
COSMOS_CACHE_SECONDS = 7 * 24 * 60 * 60


class CosmosConfigurationError(RuntimeError):
    """A conta ainda nao habilitou todas as credenciais exigidas pela Cosmos."""


class CosmosApiError(RuntimeError):
    """Erro sanitizado de transporte ou resposta da API Cosmos."""

    def __init__(self, message, *, error_code="cosmos_api_error", upstream_status=None, retryable=False):
        super().__init__(message)
        self.error_code = error_code
        self.upstream_status = upstream_status
        self.retryable = retryable


@dataclass(frozen=True)
class CosmosFiscalSuggestion:
    query: str
    matched_product: str
    gtin: str
    gpc_code: str
    gpc_description: str
    ncm: str
    ncm_description: str
    cest: str
    alternatives_count: int
    warning: str
    cached: bool = False

    def as_response(self):
        data = asdict(self)
        data["fields"] = {key: value for key, value in {"ncm": self.ncm, "cest": self.cest}.items() if value}
        return data


def get_account_cosmos_config(account):
    if account is None:
        return None
    return CosmosConfig.objects.filter(account_id=account.pk).first()


def cosmos_config_status(account):
    config = get_account_cosmos_config(account)
    return {
        "active": bool(config and config.is_active),
        "configured": bool(config and config.api_token and config.user_agent),
        "ready": bool(config and config.is_ready),
    }


def _normalize_text(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _digits(value, max_length):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return digits[:max_length]


def _value_from_mapping(value, *keys):
    if isinstance(value, dict):
        for key in keys:
            if value.get(key) not in (None, ""):
                return value[key]
        return ""
    return value or ""


def _first_cest(product):
    value = product.get("cest") or product.get("cest_code")
    if not value and isinstance(product.get("cests"), list) and product["cests"]:
        value = product["cests"][0]
    return _digits(_value_from_mapping(value, "code", "codigo", "value"), 7)


def _extract_products(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("products", "produtos", "items", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_products(value)
            if nested:
                return nested
    if any(key in payload for key in ("description", "descricao", "gtin", "ncm")):
        return [payload]
    return []


def _product_description(product):
    return str(product.get("description") or product.get("descricao") or product.get("name") or "").strip()


def _candidate_score(product, query):
    description = _normalize_text(_product_description(product))
    normalized_query = _normalize_text(query)
    if description == normalized_query:
        return (3, 1)
    query_terms = set(normalized_query.split())
    description_terms = set(description.split())
    matching_terms = len(query_terms.intersection(description_terms))
    contains_all = int(bool(query_terms) and query_terms.issubset(description_terms))
    return (2 if contains_all else 1, matching_terms)


class CosmosClient:
    def __init__(self, config):
        if not config or not config.is_active:
            raise CosmosConfigurationError("A integracao Cosmos esta desativada para esta conta.")
        if not config.api_token:
            raise CosmosConfigurationError("Token da API Cosmos nao configurado para esta conta.")
        if not config.user_agent:
            raise CosmosConfigurationError("User-Agent da Cosmos nao configurado para esta conta.")
        self.config = config

    def _get(self, path, *, params=None):
        try:
            response = requests.get(
                f"{COSMOS_API_URL}{path}",
                params=params,
                headers={
                    "X-Cosmos-Token": self.config.api_token,
                    "User-Agent": self.config.user_agent,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=self.config.timeout_seconds,
            )
        except requests.Timeout as exc:
            raise CosmosApiError(
                f"A Cosmos nao respondeu em ate {self.config.timeout_seconds} segundos. Tente novamente.",
                error_code="cosmos_timeout",
                retryable=True,
            ) from exc
        except requests.ConnectionError as exc:
            raise CosmosApiError(
                "Nao foi possivel conectar a Cosmos. Tente novamente.",
                error_code="cosmos_unavailable",
                retryable=True,
            ) from exc
        except requests.RequestException as exc:
            raise CosmosApiError(
                "Falha de comunicacao com a Cosmos. Tente novamente.",
                error_code="cosmos_request_error",
                retryable=True,
            ) from exc

        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {}
        if response.status_code >= 400:
            status_code = response.status_code
            message = "A Cosmos recusou a consulta."
            error_code = "cosmos_api_error"
            retryable = status_code == 429 or status_code >= 500
            if status_code in (401, 403):
                error_code = "cosmos_auth_error"
                message = "Token ou User-Agent recusado pela Cosmos. Confira os dados da conta."
            elif status_code == 404:
                error_code = "cosmos_not_found"
                message = "Nenhum produto correspondente foi encontrado na Cosmos."
            elif status_code == 429:
                error_code = "cosmos_rate_limited"
                message = "O limite de consultas do plano Cosmos foi atingido. Tente novamente apos a renovacao do limite."
            elif status_code >= 500:
                error_code = "cosmos_unavailable"
                message = "A Cosmos esta indisponivel no momento. Tente novamente em instantes."
            elif isinstance(data, dict):
                detail = data.get("message") or data.get("detail") or data.get("error")
                if isinstance(detail, str) and detail.strip():
                    message = detail.strip()[:500]
            raise CosmosApiError(
                message,
                error_code=error_code,
                upstream_status=status_code,
                retryable=retryable,
            )
        return data

    def suggest(self, query):
        clean_query = " ".join(str(query or "").split())
        if len(clean_query) < 3:
            raise CosmosApiError(
                "Informe ao menos 3 caracteres para pesquisar na Cosmos.",
                error_code="cosmos_invalid_query",
            )

        payload = self._get("/products", params={"query": clean_query, "page": 1, "per_page": 30})
        products = _extract_products(payload)
        if not products:
            raise CosmosApiError(
                "Nenhum produto semelhante foi encontrado na Cosmos.",
                error_code="cosmos_not_found",
                upstream_status=404,
            )
        selected = max(enumerate(products), key=lambda item: (_candidate_score(item[1], clean_query), -item[0]))[1]

        ncm_value = selected.get("ncm") or selected.get("ncm_code")
        ncm = _digits(_value_from_mapping(ncm_value, "code", "codigo", "value"), 8)
        gtin = _digits(selected.get("gtin") or selected.get("ean") or selected.get("barcode"), 14)
        # Algumas respostas de busca sao resumidas. Uma consulta ao detalhe so
        # acontece quando o resultado nao trouxe NCM, poupando a cota diaria.
        if not ncm and gtin:
            detail = self._get(f"/gtins/{gtin}.json")
            if isinstance(detail, dict):
                selected = {**selected, **detail}
                ncm_value = selected.get("ncm") or selected.get("ncm_code")
                ncm = _digits(_value_from_mapping(ncm_value, "code", "codigo", "value"), 8)

        gpc_value = selected.get("gpc") or {}
        ncm_value = selected.get("ncm") or selected.get("ncm_code") or {}
        ncm_description = (
            str(_value_from_mapping(ncm_value, "full_description", "description", "descricao"))
            if isinstance(ncm_value, dict)
            else ""
        )
        warning = (
            "Sugestao baseada no produto mais compativel encontrado. "
            "Confirme NCM e CEST com o contador antes de emitir documentos fiscais."
        )
        return CosmosFiscalSuggestion(
            query=clean_query,
            matched_product=_product_description(selected),
            gtin=gtin,
            gpc_code=str(_value_from_mapping(gpc_value, "code", "codigo", "value")),
            gpc_description=str(_value_from_mapping(gpc_value, "description", "descricao", "name")),
            ncm=ncm,
            ncm_description=ncm_description,
            cest=_first_cest(selected),
            alternatives_count=max(0, len(products) - 1),
            warning=warning,
        )


def suggest_fiscal_profile(account, query):
    config = get_account_cosmos_config(account)
    if not config:
        raise CosmosConfigurationError("A integracao Cosmos ainda nao foi configurada para esta conta.")
    clean_query = " ".join(str(query or "").split())
    fingerprint = f"{account.pk}:{config.updated_at.isoformat()}:{_normalize_text(clean_query)}"
    cache_key = f"cosmos:suggestion:{hashlib.sha256(fingerprint.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached:
        return CosmosFiscalSuggestion(**{**cached, "cached": True})
    suggestion = CosmosClient(config).suggest(clean_query)
    cache.set(cache_key, asdict(suggestion), COSMOS_CACHE_SECONDS)
    return replace(suggestion, cached=False)
