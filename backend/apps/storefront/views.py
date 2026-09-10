"""
API do storefront.

Duas superfícies bem diferentes convivem aqui:

- a **privada** (`/api/v1/storefront/...`), autenticada, com escopo por
  conta/restaurante, permissão por código e módulo E-commerce exigido;
- a **pública** (`/api/v1/public/storefront/...`), sem autenticação, que serve
  apenas conteúdo já publicado, cacheado e com throttle próprio.

Nada na superfície pública aceita escrita, e nada nela lê `draft_data`: o
rascunho é do editor, e um rascunho vazando seria a próxima campanha do
restaurante no ar antes da hora.
"""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.modules import MODULE_ECOMMERCE
from apps.core.permissions import HasModulePermission, HasTenantAccess
from apps.core.viewsets import BaseTenantViewSet
from apps.restaurants.models import Restaurant
from apps.storefront import builder_schema
from apps.storefront.builder_schema import BuilderValidationError
from apps.storefront.models import (
    MenuAsset,
    MenuDomain,
    MenuPage,
    MenuPageVersion,
    MenuSite,
    MenuTemplate,
)
from apps.storefront.permissions import (
    PERM_ASSETS,
    PERM_DOMAINS,
    PERM_EDIT,
    PERM_PUBLISH,
    PERM_VIEW,
    HasStorefrontPermission,
    StorefrontPermissionMixin,
)
from apps.storefront.serializers import (
    MenuAssetSerializer,
    MenuDomainSerializer,
    MenuPageListSerializer,
    MenuPageSerializer,
    MenuPageVersionDetailSerializer,
    MenuPageVersionSerializer,
    MenuSiteSerializer,
    MenuTemplateDetailSerializer,
    MenuTemplateSerializer,
)
from apps.storefront.services import cache as storefront_cache
from apps.storefront.services import domains as domain_service
from apps.storefront.services import publishing
from apps.storefront.services.provisioning import ensure_home_page, ensure_site
from apps.storefront.services.public_payload import build_public_payload
from apps.storefront.starter import section_presets
from apps.storefront.themes import DEFAULT_THEME_KEY, THEME_PRESETS

# A lista padrão do DRF mais a checagem por código de permissão do storefront.
STOREFRONT_PERMISSIONS = [IsAuthenticated, HasTenantAccess, HasModulePermission, HasStorefrontPermission]


def _builder_error_response(exc):
    return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)


class MenuSiteViewSet(StorefrontPermissionMixin, BaseTenantViewSet):
    """O site de cada restaurante: tema, SEO, catálogo e estado de publicação."""

    required_module = MODULE_ECOMMERCE
    permission_classes = STOREFRONT_PERMISSIONS
    serializer_class = MenuSiteSerializer
    queryset = MenuSite.objects.select_related("restaurant", "catalog").prefetch_related("domains").all()
    filterset_fields = ["is_active"]
    search_fields = ["name", "slug", "restaurant__trade_name"]
    ordering_fields = ["slug", "created_at", "updated_at"]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        # Site criado pela API também nasce com a home montada e no ar — o
        # mesmo que o provisionamento automático faz (ver services.provisioning).
        ensure_home_page(serializer.instance, user=self.request.user)

    @action(detail=False, methods=["post"], url_path="provision")
    def provision(self, request):
        """Cria o site de um restaurante que ainda não tem, já com tema e home.

        Existe para o caso em que o módulo E-commerce foi habilitado depois de
        o restaurante ser cadastrado — nesse cenário o sinal de criação já
        passou, e sem esta rota o cliente ficaria sem site nenhum.
        """
        restaurant_id = request.data.get("restaurant")
        queryset = Restaurant.all_objects.filter(deleted_at__isnull=True)
        account = getattr(request, "account", None)
        if account is not None:
            queryset = queryset.filter(account=account)
        restaurant = get_object_or_404(queryset, pk=restaurant_id)

        site = ensure_site(restaurant, user=request.user, theme_key=request.data.get("theme") or DEFAULT_THEME_KEY)
        serializer = MenuSiteSerializer(site, context=self.get_serializer_context())
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, pk=None):
        """Payload público montado a partir do RASCUNHO, para o editor pré-visualizar.

        Mesma forma da resposta pública — assim o preview usa o mesmo
        renderizador do site de verdade — mas lendo `draft_data` e sem passar
        pelo cache. Exige autenticação e permissão de leitura do storefront.
        """
        site = self.get_object()
        page_slug = request.query_params.get("page") or ""
        payload = build_public_payload(site, page_slug=page_slug or None, request=request)
        draft = (
            MenuPage.all_objects.filter(site=site, deleted_at__isnull=True)
            .filter(**({"slug": page_slug} if page_slug else {"is_home": True}))
            .first()
        )
        if draft is None:
            draft = MenuPage.all_objects.filter(site=site, deleted_at__isnull=True).order_by("display_order").first()
        if draft is not None:
            payload["page"] = {
                "id": str(draft.id),
                "title": draft.title,
                "slug": draft.slug,
                "is_home": draft.is_home,
                "seo": draft.seo or {},
                "published_at": None,
                "data": draft.draft_data or {},
            }
        payload["preview"] = True
        return Response(payload)


class MenuPageViewSet(StorefrontPermissionMixin, BaseTenantViewSet):
    """Páginas: carregar/salvar rascunho, publicar, versionar, aplicar modelo."""

    required_module = MODULE_ECOMMERCE
    permission_classes = STOREFRONT_PERMISSIONS
    serializer_class = MenuPageSerializer
    queryset = MenuPage.objects.select_related("site", "restaurant").all()
    filterset_fields = ["site", "status", "is_home"]
    search_fields = ["title", "slug"]
    ordering_fields = ["display_order", "title", "updated_at", "published_at"]
    storefront_action_permissions = {
        "publish": PERM_PUBLISH,
        "unpublish": PERM_PUBLISH,
        "versions": PERM_VIEW,
        "version_detail": PERM_VIEW,
        "restore_version": PERM_EDIT,
        "apply_template": PERM_EDIT,
    }

    def get_serializer_class(self):
        if self.action == "list":
            return MenuPageListSerializer
        return MenuPageSerializer

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        page = self.get_object()
        try:
            page = publishing.publish_page(page, user=request.user, request=request)
        except BuilderValidationError as exc:
            return _builder_error_response(exc)
        return Response(MenuPageSerializer(page, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        page = self.get_object()
        page = publishing.unpublish_page(page, user=request.user, request=request)
        return Response(MenuPageSerializer(page, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request, pk=None):
        page = self.get_object()
        queryset = MenuPageVersion.all_objects.filter(page=page, deleted_at__isnull=True).order_by("-number")
        page_of_results = self.paginate_queryset(queryset)
        serializer = MenuPageVersionSerializer(page_of_results or queryset, many=True)
        if page_of_results is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path=r"versions/(?P<version_id>[^/.]+)")
    def version_detail(self, request, pk=None, version_id=None):
        page = self.get_object()
        version = get_object_or_404(MenuPageVersion.all_objects, pk=version_id, page=page, deleted_at__isnull=True)
        return Response(MenuPageVersionDetailSerializer(version).data)

    @action(detail=True, methods=["post"], url_path=r"versions/(?P<version_id>[^/.]+)/restore")
    def restore_version(self, request, pk=None, version_id=None):
        page = self.get_object()
        version = get_object_or_404(MenuPageVersion.all_objects, pk=version_id, page=page, deleted_at__isnull=True)
        publish = str(request.data.get("publish", "")).lower() in {"1", "true", "yes"}
        if publish and not HasStorefrontPermission().has_permission(request, _PublishGate()):
            return Response(
                {"detail": "Você não tem permissão para publicar o site."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            page = publishing.restore_version(page, version, user=request.user, request=request, publish=publish)
        except BuilderValidationError as exc:
            return _builder_error_response(exc)
        return Response(MenuPageSerializer(page, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"], url_path=r"apply-template/(?P<template_id>[^/.]+)")
    def apply_template(self, request, pk=None, template_id=None):
        page = self.get_object()
        template = get_object_or_404(MenuTemplate, pk=template_id, is_active=True)
        try:
            page = publishing.apply_template(page, template, user=request.user, request=request)
        except BuilderValidationError as exc:
            return _builder_error_response(exc)
        return Response(MenuPageSerializer(page, context=self.get_serializer_context()).data)


class _PublishGate:
    """View sintética usada só para checar `storefront.publish` fora do fluxo normal."""

    def required_storefront_permission(self, request):
        return PERM_PUBLISH


class MenuTemplateViewSet(StorefrontPermissionMixin, viewsets.ReadOnlyModelViewSet):
    """Catálogo de modelos da plataforma — leitura para quem edita o site.

    Não passa pelo recorte multi-tenant porque não é dado de conta nenhuma: é
    conteúdo da plataforma, igual para todo mundo, mantido pelo /admin.
    """

    required_module = MODULE_ECOMMERCE
    permission_classes = STOREFRONT_PERMISSIONS
    serializer_class = MenuTemplateSerializer
    queryset = MenuTemplate.objects.filter(is_active=True)
    filterset_fields = ["category"]
    search_fields = ["name", "description", "category"]
    ordering_fields = ["sort_order", "name"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return MenuTemplateDetailSerializer
        return MenuTemplateSerializer


class MenuAssetViewSet(StorefrontPermissionMixin, BaseTenantViewSet):
    """Upload das imagens usadas no editor."""

    required_module = MODULE_ECOMMERCE
    permission_classes = STOREFRONT_PERMISSIONS
    serializer_class = MenuAssetSerializer
    queryset = MenuAsset.objects.select_related("restaurant").all()
    parser_classes = [MultiPartParser, FormParser]
    search_fields = ["original_name"]
    ordering_fields = ["created_at", "size"]
    throttle_scope = "storefront_assets"
    storefront_read_permission = PERM_ASSETS
    storefront_write_permission = PERM_ASSETS
    # Upload é caro (banda, storage, processamento de imagem) e é o endpoint
    # mais fácil de abusar de dentro da conta; ganha um escopo próprio de
    # throttle em vez de dividir o balde geral do usuário.
    throttle_classes = [ScopedRateThrottle]

    def get_serializer_class(self):
        return MenuAssetSerializer

    def perform_destroy(self, instance):
        # Só o registro é removido (exclusão lógica). O arquivo continua no
        # storage de propósito: uma página publicada pode estar apontando para
        # ele, e apagar o blob deixaria a foto quebrada no site do cliente. A
        # limpeza dos blobs órfãos é uma rotina à parte.
        super().perform_destroy(instance)


class MenuDomainViewSet(StorefrontPermissionMixin, BaseTenantViewSet):
    """Subdomínios da plataforma e domínios próprios apontados para o site."""

    required_module = MODULE_ECOMMERCE
    permission_classes = STOREFRONT_PERMISSIONS
    serializer_class = MenuDomainSerializer
    queryset = MenuDomain.objects.select_related("site", "restaurant").all()
    filterset_fields = ["site", "domain_type", "verified"]
    search_fields = ["hostname"]
    storefront_read_permission = PERM_DOMAINS
    storefront_write_permission = PERM_DOMAINS

    def perform_create(self, serializer):
        super().perform_create(serializer)
        storefront_cache.invalidate_domain(serializer.instance.hostname)

    def perform_update(self, serializer):
        previous = serializer.instance.hostname
        super().perform_update(serializer)
        storefront_cache.invalidate_domain(previous)
        storefront_cache.invalidate_domain(serializer.instance.hostname)

    def perform_destroy(self, instance):
        hostname = instance.hostname
        super().perform_destroy(instance)
        storefront_cache.invalidate_domain(hostname)

    @action(detail=True, methods=["get"], url_path="dns-instructions")
    def dns_instructions(self, request, pk=None):
        """O que o cliente precisa cadastrar no provedor de DNS dele."""
        domain = self.get_object()
        base = domain_service.platform_base_domain()
        records = [
            {
                "type": "TXT",
                "name": f"_starchef.{domain.hostname}",
                "value": domain.verification_token,
                "purpose": "Comprova que o domínio é seu.",
            }
        ]
        if domain.domain_type == MenuDomain.TYPE_CUSTOM and base:
            records.append(
                {
                    "type": "CNAME",
                    "name": domain.hostname,
                    "value": f"{domain.site.slug}.{base}",
                    "purpose": "Aponta o domínio para o site do cardápio.",
                }
            )
        return Response({"hostname": domain.hostname, "verified": domain.verified, "records": records})

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """Confirma a posse do domínio consultando o TXT `_starchef.<domínio>`.

        Sem `dnspython` instalado o endpoint responde 501 em vez de aprovar por
        omissão: marcar um domínio como verificado sem ter verificado nada é
        exatamente o que a verificação existe para impedir.
        """
        domain = self.get_object()
        try:
            import dns.resolver  # type: ignore
        except ImportError:
            return Response(
                {
                    "detail": "Verificação automática de DNS indisponível neste servidor.",
                    "expected_record": {
                        "type": "TXT",
                        "name": f"_starchef.{domain.hostname}",
                        "value": domain.verification_token,
                    },
                },
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        try:
            answers = dns.resolver.resolve(f"_starchef.{domain.hostname}", "TXT")
            values = {str(record).strip('"') for record in answers}
        except Exception:  # noqa: BLE001 - qualquer erro de DNS é "ainda não verificado"
            values = set()

        if domain.verification_token not in values:
            return Response(
                {"detail": "O registro TXT ainda não foi encontrado. A propagação do DNS pode levar algumas horas."},
                status=status.HTTP_409_CONFLICT,
            )

        domain.verified = True
        domain.verified_at = timezone.now()
        domain.ssl_status = MenuDomain.SSL_ISSUING
        domain.save(update_fields=["verified", "verified_at", "ssl_status", "updated_at"])
        storefront_cache.invalidate_domain(domain.hostname)
        record_audit(
            action=AuditLog.ACTION_UPDATED,
            instance=domain,
            actor=request.user,
            request=request,
            reason="Domínio do storefront verificado.",
            metadata={"storefront_action": "verify_domain", "hostname": domain.hostname},
        )
        return Response(MenuDomainSerializer(domain, context=self.get_serializer_context()).data)


class StorefrontBuilderSchemaView(APIView):
    """Contrato que o editor precisa respeitar, servido pelo próprio backend.

    O front lê daqui os blocos e as propriedades aceitas em vez de manter uma
    cópia da lista. Duas listas divergindo dariam o pior sintoma possível:
    o usuário monta a página, salva, e recebe um erro sobre um bloco que o
    editor mesmo ofereceu.
    """

    required_module = MODULE_ECOMMERCE
    permission_classes = STOREFRONT_PERMISSIONS

    def required_storefront_permission(self, request):
        return PERM_VIEW

    def get(self, request):
        return Response(
            {
                "components": sorted(builder_schema.ALLOWED_COMPONENTS),
                "data_components": sorted(builder_schema.DATA_COMPONENTS),
                "tags": sorted(builder_schema.ALLOWED_TAGS),
                "style_properties": sorted(builder_schema.ALLOWED_STYLE_PROPERTIES),
                "attributes": sorted(builder_schema.ALLOWED_ATTRIBUTES),
                "attribute_prefixes": list(builder_schema.ATTRIBUTE_PREFIXES),
                "rich_text_tags": sorted(builder_schema.RICH_TEXT_TAGS),
                "url_schemes": sorted(builder_schema.SAFE_URL_SCHEMES),
                # Seções prontas para arrastar — as MESMAS peças que montam a
                # home padrão (ver `starter.py`). Servidas daqui para o editor
                # não manter uma segunda cópia que diverge na primeira correção.
                "sections": section_presets(),
                "limits": {
                    "max_project_bytes": builder_schema.MAX_PROJECT_BYTES,
                    "max_nodes": builder_schema.MAX_NODES,
                    "max_depth": builder_schema.MAX_DEPTH,
                },
            }
        )


class StorefrontThemesView(APIView):
    """Catálogo de temas prontos, para a tela de aparência.

    O site já nasce com um deles aplicado (ver `services.provisioning`); esta
    rota existe para o cliente TROCAR de tema sem precisar entender token de
    cor. Trocar o preset é um PATCH em `theme_preset` no site.
    """

    required_module = MODULE_ECOMMERCE
    permission_classes = STOREFRONT_PERMISSIONS

    def required_storefront_permission(self, request):
        return PERM_VIEW

    def get(self, request):
        return Response(
            {
                "default": DEFAULT_THEME_KEY,
                "presets": [
                    {
                        "key": preset["key"],
                        "name": preset["name"],
                        "description": preset["description"],
                        "tokens": preset["tokens"],
                    }
                    for preset in THEME_PRESETS
                ],
            }
        )


class PublicStorefrontView(APIView):
    """`GET /api/v1/public/storefront/<slug>/` — tudo que o site precisa, publicado.

    Sem autenticação, cacheado por restaurante e invalidado a cada publicação
    (ver ``services.cache``). Aceita `?page=<slug>` para abrir uma página
    interna e `?refresh=1` não existe de propósito: o cache é derrubado por
    quem publica, não por quem visita.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_storefront"

    def _site_from_slug(self, slug):
        return (
            MenuSite.all_objects.filter(slug=slug, is_active=True, deleted_at__isnull=True)
            .select_related("restaurant", "account")
            .first()
        )

    def get(self, request, slug):
        site = self._site_from_slug(slug)
        if site is None or not site.account.is_active:
            return Response({"detail": "Cardápio não encontrado."}, status=status.HTTP_404_NOT_FOUND)

        page_slug = request.query_params.get("page") or ""
        variant = f"page:{page_slug}" if page_slug else "home"
        cached = storefront_cache.get_payload(site.restaurant_id, variant)
        if cached is not None:
            return Response(cached)

        payload = build_public_payload(site, page_slug=page_slug or None, request=request)
        storefront_cache.set_payload(site.restaurant_id, variant, payload)
        return Response(payload)


class PublicStorefrontByHostView(PublicStorefrontView):
    """Mesma resposta, resolvendo o restaurante pelo domínio da requisição.

    É o caminho que o site usa em produção: o visitante chega em
    `pizzaria.com.br` e o servidor descobre de quem é aquele host. O
    `?hostname=` existe para o renderizador server-side conseguir informar o
    host original quando ele mesmo faz a chamada.
    """

    def get(self, request):
        hostname = request.query_params.get("hostname") or domain_service.hostname_from_request(request)
        site = domain_service.resolve_site_by_hostname(hostname)
        if site is None or not site.account.is_active:
            return Response({"detail": "Cardápio não encontrado para este domínio."}, status=status.HTTP_404_NOT_FOUND)

        page_slug = request.query_params.get("page") or ""
        variant = f"page:{page_slug}" if page_slug else "home"
        cached = storefront_cache.get_payload(site.restaurant_id, variant)
        if cached is not None:
            return Response(cached)

        payload = build_public_payload(site, page_slug=page_slug or None, request=request)
        storefront_cache.set_payload(site.restaurant_id, variant, payload)
        return Response(payload)
