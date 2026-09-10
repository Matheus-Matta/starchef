"""Serializers do storefront — é aqui que o payload do editor é validado."""
import re

from django.utils.text import slugify
from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer
from apps.images.validation import validate_image_upload
from apps.storefront.builder_schema import (
    BuilderValidationError,
    validate_project_data,
    validate_header,
    validate_seo,
    validate_theme,
)
from apps.storefront.models import (
    MenuAsset,
    MenuDomain,
    MenuPage,
    MenuPageVersion,
    MenuSite,
    MenuTemplate,
)
from apps.storefront.services import domains as domain_service
from apps.storefront.starter import starter_seo
from apps.storefront.themes import DEFAULT_THEME_KEY, THEME_PRESET_KEYS, preset_key_for, theme_tokens

def _builder_error(exc):
    return serializers.ValidationError(exc.errors)


def _merge_with_instance(instance, field_name, clean):
    """Funde um PATCH parcial de `theme`/`seo` com o que já está salvo.

    `theme` e `seo` são JSONField: sem isto, um PATCH mandando só a cor
    primária REPLACES o objeto inteiro, apagando `mode`, `buttonStyle` e
    qualquer outro token que aquele formulário específico não conhecia. Um
    editor completo manda todas as chaves e não percebe a diferença; um
    formulário do painel administrativo que edita só um pedaço percebe — e
    perderia dado a cada salvamento. A fusão faz o campo se comportar como o
    resto da API: PATCH altera só o que foi enviado.
    """
    if instance is None:
        return clean
    merged = dict(getattr(instance, field_name, None) or {})
    merged.update(clean)
    return merged


class BuilderDataField(serializers.JSONField):
    """Campo JSON que só aceita a árvore de blocos depois de sanitizada.

    A sanitização acontece na *entrada*: o que fica gravado no banco já é o
    conteúdo seguro. Assim nenhuma leitura posterior — endpoint público,
    export, admin — depende de lembrar de sanitizar de novo.
    """

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        try:
            return validate_project_data(value)
        except BuilderValidationError as exc:
            raise _builder_error(exc) from exc


class MenuSiteSerializer(TenantModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)
    pages_count = serializers.IntegerField(source="pages.count", read_only=True)
    primary_domain = serializers.SerializerMethodField()

    class Meta:
        model = MenuSite
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "published_at"]

    def get_primary_domain(self, obj):
        domain = next(
            (item for item in obj.domains.all() if item.is_primary and item.verified),
            None,
        )
        return domain.hostname if domain else ""

    def validate_slug(self, value):
        slug = slugify(value or "")
        if not slug:
            raise serializers.ValidationError("Informe um endereço válido para o site.")
        return slug

    def validate_theme_preset(self, value):
        if value and value not in THEME_PRESET_KEYS:
            raise serializers.ValidationError(
                f"Tema desconhecido. Opções: {', '.join(THEME_PRESET_KEYS)}."
            )
        return value

    def validate_theme(self, value):
        try:
            clean = validate_theme(value)
        except BuilderValidationError as exc:
            raise _builder_error(exc) from exc
        return _merge_with_instance(self.instance, "theme", clean)

    def validate_seo(self, value):
        try:
            clean = validate_seo(value)
        except BuilderValidationError as exc:
            raise _builder_error(exc) from exc
        return _merge_with_instance(self.instance, "seo", clean)

    def validate_header(self, value):
        try:
            clean = validate_header(value)
        except BuilderValidationError as exc:
            raise _builder_error(exc) from exc
        # Sem merge: o cabeçalho é validado inteiro a cada gravação (os
        # sub-objetos já vêm completos de `validate_header`), então fundir com
        # o anterior só ressuscitaria chaves que o cliente acabou de limpar.
        return clean

    def validate(self, attrs):
        attrs = super().validate(attrs)
        restaurant = attrs.get("restaurant") or getattr(self.instance, "restaurant", None)
        if not attrs.get("slug") and not self.instance and restaurant:
            attrs["slug"] = slugify(restaurant.trade_name)[:140]
        catalog = attrs.get("catalog")
        if catalog and restaurant and catalog.restaurant_id != restaurant.id:
            raise serializers.ValidationError({"catalog": "O cardápio escolhido é de outro restaurante."})

        # Trocar o preset repinta o site inteiro: os tokens do preset escolhido
        # substituem o tema, a menos que a mesma requisição também mande um
        # `theme` (aí o cliente está ajustando token a token e vence).
        chosen_preset = attrs.get("theme_preset")
        preset_changed = chosen_preset and chosen_preset != getattr(self.instance, "theme_preset", "")
        if preset_changed and "theme" not in attrs:
            attrs["theme"] = theme_tokens(chosen_preset)

        if not self.instance:
            # Nenhum site nasce sem tema: sem isso, o primeiro acesso ao editor
            # mostraria uma página sem cor nenhuma, e o cliente teria de montar
            # a identidade visual antes de conseguir olhar o próprio cardápio.
            if not attrs.get("theme"):
                attrs["theme"] = theme_tokens(chosen_preset or DEFAULT_THEME_KEY)
                attrs.setdefault("theme_preset", chosen_preset or DEFAULT_THEME_KEY)
            if not attrs.get("seo") and restaurant:
                attrs["seo"] = validate_seo(starter_seo(restaurant.trade_name))
        elif "theme" in attrs and not preset_changed:
            # Tema editado à mão: o rótulo do preset só continua valendo se os
            # tokens ainda baterem exatamente com ele.
            attrs["theme_preset"] = preset_key_for(attrs["theme"])
        return attrs


class MenuPageListSerializer(TenantModelSerializer):
    """Listagem enxuta: sem o JSON do editor.

    O `draft_data` de uma página cheia tem centenas de KB. Mandá-lo na
    listagem faria a tela de páginas baixar o site inteiro para desenhar
    quatro linhas de tabela.
    """

    has_unpublished_changes = serializers.BooleanField(read_only=True)

    class Meta:
        model = MenuPage
        fields = [
            "id", "site", "restaurant", "title", "slug", "is_home", "display_order",
            "status", "published_at", "has_unpublished_changes", "seo",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "restaurant", "status", "published_at", "created_at", "updated_at"]


class MenuPageSerializer(TenantModelSerializer):
    draft_data = BuilderDataField(required=False)
    published_data = serializers.JSONField(read_only=True)
    has_unpublished_changes = serializers.BooleanField(read_only=True)
    site_slug = serializers.CharField(source="site.slug", read_only=True)

    class Meta:
        model = MenuPage
        fields = "__all__"
        # Sem os validadores automáticos de unicidade: o `UniqueTogetherValidator`
        # gerado a partir da constraint (site, slug) devolve um
        # `non_field_errors` genérico, e o formulário do editor precisa do erro
        # ancorado no campo `slug`. A regra continua valendo — em `validate`,
        # com mensagem própria, e no banco, pela constraint.
        validators = []
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS,
            # `status`, `published_data` e `published_at` mudam SÓ pela ação de
            # publicar. Se fossem graváveis, um PATCH comum marcaria a página
            # como publicada sem passar pelo versionamento nem pela permissão
            # de publicação.
            "published_data",
            "published_at",
            "published_by",
            "status",
            "restaurant",
        ]

    def validate_slug(self, value):
        slug = slugify(value or "")
        if not slug:
            raise serializers.ValidationError("Informe um endereço válido para a página.")
        return slug

    def validate_seo(self, value):
        try:
            clean = validate_seo(value)
        except BuilderValidationError as exc:
            raise _builder_error(exc) from exc
        return _merge_with_instance(self.instance, "seo", clean)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        site = attrs.get("site") or getattr(self.instance, "site", None)
        if site is None:
            raise serializers.ValidationError({"site": "Informe o site desta página."})

        request = self.context.get("request")
        account = getattr(request, "account", None) if request else None
        if account and site.account_id != account.id:
            raise serializers.ValidationError({"site": "Site de outra conta."})

        # A página herda o restaurante do site. Aceitar `restaurant` do payload
        # permitiria criar uma página "do site A" apontando para o restaurante
        # B e furar o recorte por restaurante na listagem.
        attrs["restaurant"] = site.restaurant

        if not attrs.get("slug") and not self.instance:
            attrs["slug"] = slugify(attrs.get("title", ""))[:140] or "pagina"

        slug = attrs.get("slug") or getattr(self.instance, "slug", None)
        duplicates = MenuPage.all_objects.filter(site=site, slug=slug, deleted_at__isnull=True)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"slug": "Já existe uma página com este endereço neste site."})

        if attrs.get("is_home"):
            others = MenuPage.all_objects.filter(site=site, is_home=True, deleted_at__isnull=True)
            if self.instance:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                raise serializers.ValidationError(
                    {"is_home": "Este site já tem uma página inicial. Desmarque a atual antes."}
                )
        return attrs


class MenuPageVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = MenuPageVersion
        fields = ["id", "page", "number", "label", "origin", "created_at", "created_by", "created_by_name"]
        read_only_fields = fields

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return ""
        return obj.created_by.get_full_name() or obj.created_by.get_username()


class MenuPageVersionDetailSerializer(MenuPageVersionSerializer):
    """Igual à listagem, mas com o conteúdo — usado só no retrieve."""

    class Meta(MenuPageVersionSerializer.Meta):
        fields = [*MenuPageVersionSerializer.Meta.fields, "data"]
        read_only_fields = fields


class MenuTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuTemplate
        fields = ["id", "name", "slug", "description", "category", "preview_image", "is_active", "sort_order"]
        read_only_fields = fields


class MenuTemplateDetailSerializer(MenuTemplateSerializer):
    class Meta(MenuTemplateSerializer.Meta):
        fields = [*MenuTemplateSerializer.Meta.fields, "project_data"]
        read_only_fields = fields


class MenuAssetSerializer(TenantModelSerializer):
    url = serializers.CharField(read_only=True)

    class Meta:
        model = MenuAsset
        fields = [
            "id", "restaurant", "file", "url", "original_name", "content_type",
            "size", "width", "height", "checksum", "created_at", "created_by",
        ]
        read_only_fields = [
            "id", "url", "original_name", "content_type", "size", "width",
            "height", "checksum", "created_at", "created_by",
        ]
        extra_kwargs = {"file": {"write_only": True}}

    def validate_file(self, uploaded):
        from django.conf import settings

        max_bytes = getattr(settings, "STOREFRONT_ASSET_MAX_BYTES", 8 * 1024 * 1024)
        uploaded._starchef_image_metadata = validate_image_upload(uploaded, max_bytes=max_bytes)
        return uploaded

    def validate(self, attrs):
        attrs = super().validate(attrs)
        uploaded = attrs.get("file")
        if uploaded is None:
            return attrs

        attrs.update(uploaded._starchef_image_metadata)
        return attrs


class MenuDomainSerializer(TenantModelSerializer):
    site_slug = serializers.CharField(source="site.slug", read_only=True)

    class Meta:
        model = MenuDomain
        fields = "__all__"
        read_only_fields = [
            *AUDIT_READ_ONLY_FIELDS,
            # Verificação é resultado de checar o DNS, nunca de o cliente
            # afirmar que verificou.
            "verified",
            "verified_at",
            "verification_token",
            "ssl_status",
            "restaurant",
        ]

    def validate_hostname(self, value):
        hostname = domain_service.normalize_hostname(value)
        if not domain_service.is_valid_hostname(hostname):
            raise serializers.ValidationError("Informe um domínio válido (ex.: cardapio.seurestaurante.com.br).")
        if hostname in domain_service.reserved_hostnames():
            raise serializers.ValidationError("Este domínio é reservado pela plataforma.")
        if re.search(r"[^a-z0-9.-]", hostname):
            raise serializers.ValidationError("O domínio contém caracteres inválidos.")
        return hostname

    def validate(self, attrs):
        attrs = super().validate(attrs)
        site = attrs.get("site") or getattr(self.instance, "site", None)
        if site is None:
            raise serializers.ValidationError({"site": "Informe o site deste domínio."})
        attrs["restaurant"] = site.restaurant

        hostname = attrs.get("hostname") or getattr(self.instance, "hostname", "")
        base = domain_service.platform_base_domain()
        domain_type = attrs.get("domain_type") or getattr(self.instance, "domain_type", MenuDomain.TYPE_SUBDOMAIN)
        if domain_type == MenuDomain.TYPE_SUBDOMAIN and base and not hostname.endswith("." + base):
            raise serializers.ValidationError(
                {"hostname": f"Um subdomínio da plataforma precisa terminar em .{base}."}
            )

        existing = MenuDomain.all_objects.filter(hostname=hostname, deleted_at__isnull=True)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError({"hostname": "Este domínio já está em uso."})

        if not self.instance:
            attrs["verification_token"] = domain_service.new_verification_token()
        return attrs
