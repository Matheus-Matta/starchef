from django.db import models

from apps.core.models import TenantModel

UNIT_UNIT = "unit"
UNIT_KG = "kg"
UNIT_G = "g"
UNIT_L = "l"
UNIT_ML = "ml"

# Vocabulario unico de unidades. Fica no modulo, e nao dentro de `Ingredient`,
# porque `ProductAddon` e `Product` — declarados antes dele — tambem precisam
# declarar em que unidade escrevem o consumo. Ver `apps.menu.units` para a
# conversao entre elas.
UNIT_CHOICES = [
    (UNIT_UNIT, "Unit"),
    (UNIT_KG, "Kg"),
    (UNIT_G, "g"),
    (UNIT_L, "L"),
    (UNIT_ML, "ml"),
]


class ProductCategory(TenantModel):
    # Categorias são compartilhadas entre restaurantes (reutilizáveis): o vínculo
    # de restaurante é opcional. Sobrescreve o FK obrigatório do TenantModel.
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=120)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.SET_NULL)
    display_order = models.PositiveIntegerField(default=0)
    logo_image = models.ForeignKey(
        "images.Image",
        null=True,
        blank=True,
        related_name="category_logos",
        on_delete=models.SET_NULL,
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["display_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name", "parent"], name="unique_category_by_branch_parent"),
        ]

    def __str__(self):
        return self.name


class Product(TenantModel):
    TYPE_MEAL = "meal"
    TYPE_DRINK = "drink"
    TYPE_DESSERT = "dessert"
    TYPE_COMBO = "combo"
    TYPE_ADDON = "addon"
    TYPE_INPUT = "input"

    TYPE_CHOICES = [
        (TYPE_MEAL, "Meal"),
        (TYPE_DRINK, "Drink"),
        (TYPE_DESSERT, "Dessert"),
        (TYPE_COMBO, "Combo"),
        (TYPE_ADDON, "Addon"),
        (TYPE_INPUT, "Input"),
    ]

    SECTOR_KITCHEN = "kitchen"
    SECTOR_BAR = "bar"
    SECTOR_DESSERT = "dessert"

    SECTOR_CHOICES = [
        (SECTOR_KITCHEN, "Kitchen"),
        (SECTOR_BAR, "Bar"),
        (SECTOR_DESSERT, "Dessert"),
    ]

    PRICING_UNIT = "unit"
    PRICING_KG = "kg"

    PRICING_CHOICES = [
        (PRICING_UNIT, "Por unidade"),
        (PRICING_KG, "Por kilo"),
    ]

    name = models.CharField(max_length=180, db_index=True)
    restaurants = models.ManyToManyField(
        "restaurants.Restaurant",
        related_name="available_products",
        blank=True,
        help_text="Restaurantes da conta que podem comercializar este produto.",
    )
    internal_code = models.CharField(max_length=60)
    # Código de barras do fabricante (GTIN-8/12/13/14) ou etiqueta própria.
    #
    # TEXTO, nunca número: `0000012345670` e `12345670` são códigos
    # diferentes, e guardar como número perderia os zeros à esquerda — o
    # leitor mandaria o código impresso e o PDV não acharia o produto.
    #
    # Único na CONTA (ver constraint): se dois produtos tivessem o mesmo
    # código, o PDV teria de escolher um em silêncio na hora da venda.
    ean = models.CharField(
        max_length=32,
        blank=True,
        default="",
        db_index=True,
        help_text="Código de barras (EAN/GTIN). Opcional, único na conta.",
    )
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        ProductCategory,
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )
    image = models.ImageField(upload_to="products/", blank=True)
    logo_image = models.ForeignKey(
        "images.Image",
        null=True,
        blank=True,
        related_name="product_logos",
        on_delete=models.SET_NULL,
    )
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Por unidade, ou por kg quando pricing_unit=kg.")
    promotional_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    pricing_unit = models.CharField(max_length=8, choices=PRICING_CHOICES, default=PRICING_UNIT)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    margin_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    product_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MEAL)
    sector = models.ForeignKey(
        "restaurants.TableSector",
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )
    # Grupo tributario (CFOP/CSOSN/NCM). Se vazio, usa o perfil padrao da filial.
    fiscal_profile = models.ForeignKey(
        "invoices.FiscalProfile",
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )
    average_preparation_time = models.PositiveIntegerField(default=15, help_text="Minutes")
    production_sector = models.CharField(max_length=20, choices=SECTOR_CHOICES, default=SECTOR_KITCHEN)
    controls_stock = models.BooleanField(default=False)
    # Produto vendido direto da prateleira (refrigerante em lata, agua): nao
    # tem ficha tecnica, mas move saldo. Sem este vinculo, `controls_stock`
    # ficava marcado e nao baixava nada — a promessa do campo nao se cumpria.
    stock_ingredient = models.ForeignKey(
        "menu.Ingredient",
        null=True,
        blank=True,
        related_name="direct_products",
        on_delete=models.PROTECT,
        help_text="Insumo consumido por unidade vendida, para produtos sem ficha tecnica.",
    )
    stock_consumption_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    stock_consumption_unit = models.CharField(max_length=12, choices=UNIT_CHOICES, blank=True)
    allows_addons = models.BooleanField(default=True)
    allows_notes = models.BooleanField(default=True)
    requires_variation = models.BooleanField(
        default=False,
        help_text="Exige que o operador escolha uma das variacoes ativas antes de adicionar o produto ao pedido.",
    )
    available_for_table = models.BooleanField(default=True)
    available_for_counter = models.BooleanField(default=True)
    available_for_delivery = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["category__display_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "internal_code"], name="unique_product_code_by_branch"),
            # Vazio não conflita (a maioria dos produtos não tem código de
            # barras); preenchido, é único na conta inteira — o leitor não
            # sabe de qual filial é o produto que ele acabou de ler.
            models.UniqueConstraint(
                fields=["account", "ean"],
                condition=~models.Q(ean="") & models.Q(deleted_at__isnull=True),
                name="unique_product_ean_by_account",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "is_active", "product_type"]),
            models.Index(fields=["branch", "production_sector"]),
            # O PDV busca por código na venda: sem índice, cada leitura
            # varreria o catálogo inteiro.
            models.Index(fields=["account", "ean"]),
        ]

    @property
    def current_price(self):
        return self.promotional_price or self.sale_price

    @property
    def is_weighed(self):
        return self.pricing_unit == self.PRICING_KG

    def __str__(self):
        return self.name


class ProductVariation(TenantModel):
    product = models.ForeignKey(Product, related_name="variations", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    price_delta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    logo_image = models.ForeignKey(
        "images.Image",
        null=True,
        blank=True,
        related_name="variation_logos",
        on_delete=models.SET_NULL,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="unique_variation_by_product"),
        ]

    def __str__(self):
        return f"{self.product} - {self.name}"


class ProductAddon(TenantModel):
    # Adicionais são compartilhados entre restaurantes (reutilizáveis): o vínculo
    # de restaurante é opcional. Sobrescreve o FK obrigatório do TenantModel.
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=120)
    products = models.ManyToManyField(Product, blank=True, related_name="addons")
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    production_sector = models.CharField(max_length=20, choices=Product.SECTOR_CHOICES, default=Product.SECTOR_KITCHEN)
    # O adicional continua sendo uma oferta comercial; o vinculo abaixo diz o
    # que ele consome fisicamente. Sem ele, "bacon extra" vendia sem tirar
    # bacon nenhum do estoque, e a diferenca so aparecia no inventario.
    ingredient = models.ForeignKey(
        "menu.Ingredient",
        null=True,
        blank=True,
        related_name="addons",
        on_delete=models.PROTECT,
        help_text="Insumo consumido por unidade vendida deste adicional.",
    )
    consumption_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    consumption_unit = models.CharField(max_length=12, choices=UNIT_CHOICES, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_addon_by_branch"),
        ]

    def __str__(self):
        return self.name


class Ingredient(TenantModel):
    # Aliases do vocabulario do modulo — o codigo existente (e as migrations)
    # referenciam `Ingredient.UNIT_*`, entao eles continuam valendo.
    UNIT_UNIT = UNIT_UNIT
    UNIT_KG = UNIT_KG
    UNIT_G = UNIT_G
    UNIT_L = UNIT_L
    UNIT_ML = UNIT_ML

    UNIT_CHOICES = UNIT_CHOICES

    # O insumo é cadastro da CONTA, não do restaurante: "farinha" é a mesma
    # farinha em toda a rede, e duplicá-la por unidade só fazia o mesmo item
    # aparecer várias vezes na busca. Quem localiza o estoque é o ARMAZÉM
    # (`StockLocation`), que continua pertencendo a um restaurante — o saldo
    # de uma unidade é a soma do que está nos armazéns dela.
    # Sobrescreve o FK obrigatório do TenantModel.
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="%(class)s_set",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=12, choices=UNIT_CHOICES, default=UNIT_UNIT)
    supplier = models.ForeignKey(
        "stock.Supplier",
        null=True,
        blank=True,
        related_name="ingredients",
        on_delete=models.PROTECT,
        help_text="Fornecedor padrao sugerido nas entradas deste insumo.",
    )
    average_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    # Estoque mínimo é opcional (STC-031): campo do Módulo Logística. Pode ficar
    # vazio (null) quando a logística não é usada; quando informado, não pode ser negativo.
    minimum_stock = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            # Nome único na CONTA. A condição existe porque o projeto usa
            # exclusão lógica: sem ela, um insumo apagado impediria para
            # sempre que outro com o mesmo nome fosse cadastrado.
            models.UniqueConstraint(
                fields=["account", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_ingredient_by_account",
            ),
        ]
        indexes = [
            models.Index(fields=["account", "is_active"]),
        ]

    def __str__(self):
        return self.name


class Recipe(TenantModel):
    product = models.OneToOneField(Product, related_name="recipe", on_delete=models.CASCADE)
    yield_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    preparation_instructions = models.TextField(blank=True, default="")
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    auto_deduct_stock = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Recipe - {self.product}"


class RecipeItem(TenantModel):
    recipe = models.ForeignKey(Recipe, related_name="items", on_delete=models.CASCADE)
    ingredient = models.ForeignKey(Ingredient, related_name="recipe_items", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=12, choices=Ingredient.UNIT_CHOICES)
    ingredient_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["recipe", "ingredient"], name="unique_ingredient_by_recipe"),
        ]

    def __str__(self):
        return f"{self.recipe} - {self.ingredient}"


class Menu(TenantModel):
    """Uma lista ordenada de itens — no mesmo espirito dos menus do Shopify.

    Um menu nao e "o cardapio": e uma **colecao nomeada** que o restaurante
    monta e o site consome. O mesmo modelo serve a quatro coisas que antes
    exigiriam quatro cadastros:

    - a barra de navegacao do cabecalho (com submenus);
    - o carrossel de banners da home;
    - uma vitrine de categorias ou de produtos escolhidos a dedo;
    - a curadoria de catalogo (quais produtos entram em cada canal), que e o
      uso que `MenuSite.catalog` ja fazia.

    O bloco do storefront aponta para um menu pelo id; quem decide o conteudo
    e a ordem e o restaurante, aqui, sem abrir o editor visual. E o que da ao
    cliente controle sobre o que aparece no banner e no menu do topo.

    `menu_type` e uma DICA de proposito, nao uma trava: filtra o que o editor
    sugere em cada bloco (nao faz sentido oferecer um menu de banners para a
    barra de navegacao), mas qualquer menu continua utilizavel em qualquer
    bloco — uma regra rigida aqui so criaria um cadastro duplicado no dia em
    que alguem quisesse reaproveitar uma lista.
    """

    CHANNEL_ALL = "all"
    CHANNEL_TABLE = "table"
    CHANNEL_DELIVERY = "delivery"
    CHANNEL_COUNTER = "counter"
    CHANNEL_DIGITAL = "digital"

    CHANNEL_CHOICES = [
        (CHANNEL_ALL, "All channels"),
        (CHANNEL_TABLE, "Dine-in / Table"),
        (CHANNEL_DELIVERY, "Delivery"),
        (CHANNEL_COUNTER, "Counter"),
        (CHANNEL_DIGITAL, "Digital / QR Code"),
    ]

    TYPE_CATALOG = "catalog"
    TYPE_NAVIGATION = "navigation"
    TYPE_BANNER = "banner"
    TYPE_SHOWCASE = "showcase"

    TYPE_CHOICES = [
        (TYPE_CATALOG, "Catalogo (curadoria de produtos)"),
        (TYPE_NAVIGATION, "Navegacao (cabecalho, rodape)"),
        (TYPE_BANNER, "Banners (carrossel)"),
        (TYPE_SHOWCASE, "Vitrine (categorias ou produtos em destaque)"),
    ]

    # De onde saem os itens. `manual` é a lista que o restaurante monta à mão;
    # as demais são consultas resolvidas na hora de renderizar.
    SOURCE_MANUAL = "manual"
    SOURCE_ALL_CATEGORIES = "all_categories"
    SOURCE_CATEGORY_PRODUCTS = "category_products"
    SOURCE_BEST_SELLERS = "best_sellers"
    SOURCE_PROMOTIONS = "promotions"

    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Itens escolhidos a mao"),
        (SOURCE_ALL_CATEGORIES, "Todas as categorias ativas"),
        (SOURCE_CATEGORY_PRODUCTS, "Produtos de uma categoria"),
        (SOURCE_BEST_SELLERS, "Mais vendidos"),
        (SOURCE_PROMOTIONS, "Em promocao"),
    ]

    name = models.CharField(max_length=120)
    # "Handle", no vocabulário do Shopify: o apelido estável do menu, usado
    # pelos blocos para apontar para ele. Único por CONTA, e não globalmente —
    # duas contas podem ter, cada uma, o seu menu "principal", e antes a
    # primeira que criasse travava o nome para toda a plataforma.
    slug = models.SlugField(max_length=140)
    menu_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_CATALOG, db_index=True)
    source = models.CharField(max_length=24, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    # Só para `source = category_products`.
    source_category = models.ForeignKey(
        "menu.ProductCategory",
        null=True,
        blank=True,
        related_name="source_of_menus",
        on_delete=models.CASCADE,
    )
    # Teto de itens das origens dinâmicas (0 = sem limite).
    item_limit = models.PositiveIntegerField(default=0)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_ALL)
    is_active = models.BooleanField(default=True, db_index=True)
    available_from = models.TimeField(null=True, blank=True)
    available_until = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_menu_name_by_branch"),
            models.UniqueConstraint(
                fields=["account", "slug"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_menu_slug_by_account",
            ),
        ]
        indexes = [
            models.Index(fields=["account", "menu_type", "is_active"]),
        ]

    def __str__(self):
        return self.name

    @property
    def is_dynamic(self):
        return self.source != self.SOURCE_MANUAL


class MenuItem(TenantModel):
    """Uma entrada de menu: o que mostrar e para onde levar.

    O tipo diz o que a entrada **é**; o destino diz para onde ela **leva**, e
    os dois nem sempre coincidem — um banner é uma imagem que leva a uma
    categoria. Por isso `image` e `url` existem em todos os tipos, em vez de
    quatro modelos separados:

    | tipo       | mostra                        | leva para                    |
    | ---------- | ----------------------------- | ---------------------------- |
    | `product`  | o produto (nome, foto, preco) | a pagina do produto          |
    | `category` | a categoria                   | a listagem daquela categoria |
    | `image`    | a imagem enviada aqui         | o `url` informado (ou nada)  |
    | `custom`   | so o titulo                   | o `url` informado            |

    `image` preenchida num item de produto/categoria **substitui** a foto
    padrão: é assim que o restaurante põe uma arte de campanha no carrossel
    sem trocar a foto do produto no cardápio.

    Aninhamento (`parent`) existe para os submenus da barra de navegação, e
    para no terceiro nível — o mesmo teto do Shopify. Não é limitação técnica:
    menu com quatro níveis não cabe em tela de celular, e quem monta um só
    descobre isso depois de publicado.
    """

    TYPE_PRODUCT = "product"
    TYPE_CATEGORY = "category"
    TYPE_IMAGE = "image"
    TYPE_CUSTOM = "custom"

    TYPE_CHOICES = [
        (TYPE_PRODUCT, "Produto"),
        (TYPE_CATEGORY, "Categoria"),
        (TYPE_IMAGE, "Imagem / banner"),
        (TYPE_CUSTOM, "Link personalizado"),
    ]

    MAX_DEPTH = 3

    menu = models.ForeignKey(Menu, related_name="items", on_delete=models.CASCADE)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
        help_text="Item pai, para submenus da barra de navegacao.",
    )
    item_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PRODUCT, db_index=True)

    # Rótulo. Vazio herda o nome do produto/categoria — assim, renomear o
    # produto renomeia a entrada do menu, que é o que espera quem nunca
    # digitou um título aqui.
    title = models.CharField(max_length=180, blank=True, default="")
    subtitle = models.CharField(max_length=255, blank=True, default="")

    product = models.ForeignKey(
        Product, null=True, blank=True, related_name="menu_items", on_delete=models.CASCADE
    )
    category = models.ForeignKey(
        "menu.ProductCategory", null=True, blank=True, related_name="menu_items", on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to="menu/items/", blank=True)
    url = models.CharField(max_length=500, blank=True, default="")
    opens_in_new_tab = models.BooleanField(default=False)

    display_order = models.PositiveIntegerField(default=0)
    # Preço só deste menu (uso de catálogo: a mesma pizza mais cara no
    # delivery). Vale apenas para item de produto.
    override_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "created_at"]
        indexes = [
            models.Index(fields=["menu", "parent", "display_order"]),
            models.Index(fields=["menu", "item_type"]),
        ]

    def __str__(self):
        return f"{self.menu} -> {self.label}"

    @property
    def label(self):
        """O texto exibido: o título informado, ou o nome do alvo."""
        if self.title:
            return self.title
        if self.item_type == self.TYPE_PRODUCT and self.product_id:
            return self.product.name
        if self.item_type == self.TYPE_CATEGORY and self.category_id:
            return self.category.name
        return self.url or "Item"

    @property
    def depth(self):
        """1 para item de topo. Sobe pelos pais, com teto para não travar
        num ciclo que tenha escapado da validação."""
        level = 1
        node = self.parent
        while node is not None and level <= self.MAX_DEPTH + 1:
            level += 1
            node = node.parent
        return level

