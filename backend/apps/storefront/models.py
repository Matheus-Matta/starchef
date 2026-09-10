"""
Modelos do cardápio digital editável (storefront).

O storefront é o site público do restaurante, montado no editor visual de
blocos do painel. O backend guarda três coisas e nada além disso:

1. **apresentação** — a árvore de blocos do editor (`MenuPage.draft_data` /
   `published_data`), sempre validada e sanitizada antes de ser persistida
   (ver ``apps.storefront.builder_schema``);
2. **identidade do site** — tema, SEO, domínio e páginas (`MenuSite`,
   `MenuDomain`);
3. **acervo** — imagens enviadas pelo editor (`MenuAsset`).

Regra de ouro: o JSON do editor **não** guarda cópia de produto, preço, taxa
de entrega, horário nem qualquer regra de negócio. Um bloco de vitrine guarda
apenas a *configuração* ("mostre a categoria X em 4 colunas"); os dados reais
continuam saindo de ``apps.menu``/``apps.restaurants`` no endpoint público
consolidado.

Todos os modelos carregam `restaurant` — inclusive os que poderiam derivá-lo
do pai. Isso não é redundância: o ``TenantQuerySetMixin`` recorta o queryset
pelo campo `restaurant` do próprio model, então sem ele um usuário de um
restaurante enxergaria as páginas de outro restaurante da mesma conta.
"""
import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TenantBaseModel, TimeStampedModel


def asset_upload_path(instance, filename):
    """`storefront/<restaurant>/<uuid>.<ext>` — o nome do arquivo nunca vem do cliente.

    O nome original é preservado em `original_name` só para exibição; o caminho
    real é sempre um UUID, o que elimina de uma vez path traversal, colisão de
    nome e caracteres estranhos no bucket.
    """
    suffix = ""
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()[:10]
    return f"storefront/{instance.restaurant_id}/{uuid.uuid4().hex}{suffix}"


class MenuSite(TenantBaseModel):
    """O site público de um restaurante (um por restaurante)."""

    restaurant = models.OneToOneField(
        "restaurants.Restaurant",
        related_name="menu_site",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=150, blank=True, default="")
    # Slug global: é o endereço público (`/api/v1/public/storefront/<slug>/`) e
    # o rótulo do subdomínio. Dois restaurantes não podem disputá-lo, nem mesmo
    # em contas diferentes.
    slug = models.SlugField(max_length=140, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    # Catálogo curado que alimenta os blocos de vitrine. Quando vazio, o
    # endpoint público publica todos os produtos ativos do restaurante.
    catalog = models.ForeignKey(
        "menu.Menu",
        null=True,
        blank=True,
        related_name="storefront_sites",
        on_delete=models.SET_NULL,
        help_text="Cardápio (menu.Menu) que define quais produtos aparecem no site.",
    )
    theme = models.JSONField(default=dict, blank=True)
    # Qual preset de `themes.py` originou o tema atual. É só um rótulo para a
    # interface poder marcar o tema ativo e oferecer "voltar ao original" — a
    # verdade continua sendo `theme`, que o cliente edita token a token. Fica
    # vazio quando o tema foi customizado a ponto de não corresponder a nenhum.
    theme_preset = models.CharField(max_length=40, blank=True, default="")
    seo = models.JSONField(default=dict, blank=True)
    # Cabeçalho do site: faixa de aviso, logo, endereço de entrega, busca,
    # ações e QUAL MENU alimenta a navegação. Mora aqui, e não numa árvore de
    # blocos, porque é o único elemento presente em todas as páginas — um
    # clique errado no editor não pode apagá-lo. O que ele MOSTRA continua
    # configurável; só o "existir" é que não está em disputa.
    header = models.JSONField(default=dict, blank=True)
    # Espelha o que o público vê: preenchido na primeira publicação de página.
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["slug"]
        indexes = [
            models.Index(fields=["account", "is_active"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return self.name or self.slug


class MenuPage(TenantBaseModel):
    """Uma página do site, com rascunho e versão publicada separados."""

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Rascunho"),
        (STATUS_PUBLISHED, "Publicada"),
        (STATUS_ARCHIVED, "Arquivada"),
    ]

    site = models.ForeignKey(MenuSite, related_name="pages", on_delete=models.CASCADE)
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        related_name="menu_pages",
        on_delete=models.PROTECT,
    )
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=140)
    # A página inicial do site: é a que o endpoint público devolve quando
    # nenhum slug de página é pedido.
    is_home = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    # `draft_data` é o que o editor abre e salva; `published_data` é o que o
    # público lê. Salvar no editor NUNCA publica — são campos distintos de
    # propósito.
    draft_data = models.JSONField(default=dict, blank=True)
    published_data = models.JSONField(default=dict, blank=True)
    seo = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="storefront_pages_published",
        on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ["display_order", "title"]
        constraints = [
            models.UniqueConstraint(fields=["site", "slug"], name="unique_menu_page_slug_per_site"),
            models.UniqueConstraint(
                fields=["site"],
                condition=models.Q(is_home=True),
                name="unique_menu_page_home_per_site",
            ),
        ]
        indexes = [
            models.Index(fields=["site", "status"]),
            models.Index(fields=["account", "restaurant"]),
        ]

    def __str__(self):
        return f"{self.site} / {self.slug}"

    @property
    def has_unpublished_changes(self):
        return self.draft_data != self.published_data


class MenuPageVersion(TenantBaseModel):
    """Instantâneo imutável do conteúdo de uma página.

    Gravado ANTES de cada publicação (guardando o que estava no ar) e antes de
    cada restauração, para que nenhuma publicação seja um caminho sem volta.
    """

    ORIGIN_PUBLISH = "publish"
    ORIGIN_RESTORE = "restore"
    ORIGIN_MANUAL = "manual"

    ORIGIN_CHOICES = [
        (ORIGIN_PUBLISH, "Publicação"),
        (ORIGIN_RESTORE, "Restauração"),
        (ORIGIN_MANUAL, "Manual"),
    ]

    page = models.ForeignKey(MenuPage, related_name="versions", on_delete=models.CASCADE)
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        related_name="menu_page_versions",
        on_delete=models.PROTECT,
    )
    number = models.PositiveIntegerField(default=1)
    label = models.CharField(max_length=150, blank=True, default="")
    origin = models.CharField(max_length=20, choices=ORIGIN_CHOICES, default=ORIGIN_PUBLISH)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["page", "number"], name="unique_page_version_number"),
        ]
        indexes = [
            models.Index(fields=["page", "number"]),
        ]

    def __str__(self):
        return f"{self.page} v{self.number}"


class MenuTemplate(TimeStampedModel):
    """Modelo pronto de página, do catálogo da plataforma.

    Não é multi-tenant de propósito: é conteúdo da plataforma, mantido pelo
    /admin e apenas *copiado* para a página — depois de aplicado não sobra
    vínculo algum entre a página e o template.
    """

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=60, blank=True, default="")
    preview_image = models.URLField(blank=True, default="")
    project_data = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class MenuAsset(TenantBaseModel):
    """Arquivo enviado pelo editor (banner, logo, foto de prato).

    Existe para que o JSON do editor guarde uma URL, e não um base64: um
    `data:` embutido incharia o rascunho até o ponto de a página não abrir
    mais, e nenhuma dessas imagens poderia ser servida por CDN.
    """

    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        related_name="menu_assets",
        on_delete=models.PROTECT,
    )
    file = models.FileField(upload_to=asset_upload_path, max_length=400)
    original_name = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=100, blank=True, default="")
    size = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "restaurant"]),
            models.Index(fields=["restaurant", "checksum"]),
        ]

    def __str__(self):
        return self.original_name or str(self.file)

    @property
    def url(self):
        try:
            return self.file.url
        except ValueError:
            return ""


class MenuDomain(TenantBaseModel):
    """Subdomínio da plataforma ou domínio próprio apontado para o site."""

    TYPE_SUBDOMAIN = "subdomain"
    TYPE_CUSTOM = "custom"

    TYPE_CHOICES = [
        (TYPE_SUBDOMAIN, "Subdomínio"),
        (TYPE_CUSTOM, "Domínio próprio"),
    ]

    SSL_PENDING = "pending"
    SSL_ISSUING = "issuing"
    SSL_ACTIVE = "active"
    SSL_ERROR = "error"

    SSL_CHOICES = [
        (SSL_PENDING, "Pendente"),
        (SSL_ISSUING, "Emitindo"),
        (SSL_ACTIVE, "Ativo"),
        (SSL_ERROR, "Erro"),
    ]

    site = models.ForeignKey(MenuSite, related_name="domains", on_delete=models.CASCADE)
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        related_name="menu_domains",
        on_delete=models.PROTECT,
    )
    # Sempre minúsculo e sem porta (normalizado no serializer): o hostname é a
    # chave de busca do site na requisição pública, e "Pizzaria.com" e
    # "pizzaria.com" são o mesmo host para o navegador.
    hostname = models.CharField(max_length=255, unique=True)
    domain_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_SUBDOMAIN)
    is_primary = models.BooleanField(default=False)
    verified = models.BooleanField(default=False)
    verification_token = models.CharField(max_length=64, blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    ssl_status = models.CharField(max_length=30, choices=SSL_CHOICES, default=SSL_PENDING)

    class Meta:
        ordering = ["hostname"]
        constraints = [
            models.UniqueConstraint(
                fields=["site"],
                condition=models.Q(is_primary=True),
                name="unique_primary_domain_per_site",
            ),
        ]
        indexes = [
            models.Index(fields=["hostname", "verified"]),
        ]

    def __str__(self):
        return self.hostname
