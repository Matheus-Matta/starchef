"""
Resolução do site a partir do hostname da requisição.

O storefront pode ser servido em `pizzaria.starchef.app` (subdomínio da
plataforma) ou em `pizzariaitalia.com.br` (domínio próprio do cliente). Em
ambos os casos, quem chega na API pública traz apenas o host — e é preciso
descobrir de qual restaurante é aquele site antes de montar qualquer resposta.

Essa tradução é cacheada, inclusive o resultado negativo: um host desconhecido
(varredura, domínio apontado por engano, bot) não pode virar uma consulta ao
banco por requisição.
"""
import re
import secrets

from django.conf import settings

from apps.storefront.services import cache as storefront_cache

_HOSTNAME_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")
# Sentinela do cache negativo: `None` no cache é indistinguível de "não
# cacheado", e é justamente o caso que mais se repete.
_NOT_FOUND = "__none__"


def normalize_hostname(value):
    """Minúsculo, sem porta, sem ponto final, sem esquema."""
    if not value:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"^[a-z]+://", "", text)
    text = text.split("/")[0]
    text = text.split(":")[0]
    return text.rstrip(".")


def is_valid_hostname(value):
    hostname = normalize_hostname(value)
    return bool(hostname) and len(hostname) <= 255 and bool(_HOSTNAME_RE.match(hostname))


def reserved_hostnames():
    """Hosts da própria plataforma — não podem ser reivindicados como domínio."""
    configured = getattr(settings, "STOREFRONT_RESERVED_HOSTNAMES", "") or ""
    if isinstance(configured, str):
        configured = [item for item in re.split(r"[,\s]+", configured) if item]
    return {normalize_hostname(item) for item in configured} | {"localhost"}


def platform_base_domain():
    return normalize_hostname(getattr(settings, "STOREFRONT_BASE_DOMAIN", ""))


def new_verification_token():
    """Token que o cliente publica em TXT `_starchef.<domínio>` para provar posse."""
    return f"starchef-verify-{secrets.token_hex(16)}"


def hostname_from_request(request):
    """Host público da requisição.

    Confia no `X-Forwarded-Host` só porque o proxy TLS que termina o storefront
    é da própria infraestrutura; o `Host` continua valendo quando não há proxy.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_HOST", "")
    if forwarded:
        return normalize_hostname(forwarded.split(",")[0])
    return normalize_hostname(request.get_host())


def resolve_site_by_hostname(hostname):
    """Devolve o ``MenuSite`` ativo daquele host, ou ``None``.

    Um domínio precisa estar **verificado** para servir conteúdo: sem isso,
    apontar um CNAME para a plataforma bastaria para servir o cardápio de
    outra pessoa num domínio qualquer.
    """
    from apps.storefront.models import MenuDomain, MenuSite

    hostname = normalize_hostname(hostname)
    if not hostname:
        return None

    cached = storefront_cache.get_domain(hostname)
    if cached == _NOT_FOUND:
        return None
    if cached:
        site = (
            MenuSite.all_objects.filter(slug=cached, is_active=True, deleted_at__isnull=True)
            .select_related("restaurant", "account")
            .first()
        )
        if site:
            return site

    candidates = [hostname]
    if hostname.startswith("www."):
        candidates.append(hostname[4:])

    domain = (
        MenuDomain.all_objects.filter(hostname__in=candidates, verified=True, deleted_at__isnull=True)
        .select_related("site__restaurant", "site__account")
        .order_by("-is_primary")
        .first()
    )
    site = domain.site if domain else None

    # Subdomínio da plataforma resolve pelo slug do site, sem exigir um
    # MenuDomain cadastrado: `<slug>.starchef.app` é sempre do site `<slug>`.
    base = platform_base_domain()
    if site is None and base and hostname.endswith("." + base):
        label = hostname[: -(len(base) + 1)].split(".")[-1]
        site = (
            MenuSite.all_objects.filter(slug=label, is_active=True, deleted_at__isnull=True)
            .select_related("restaurant", "account")
            .first()
        )

    if site is None or not site.is_active or site.deleted_at is not None:
        storefront_cache.set_domain(hostname, _NOT_FOUND)
        return None

    storefront_cache.set_domain(hostname, site.slug)
    return site
