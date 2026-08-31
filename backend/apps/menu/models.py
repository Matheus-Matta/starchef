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

    # Ingredientes são compartilhados entre restaurantes (reutilizáveis): o vínculo
    # de restaurante é opcional. Sobrescreve o FK obrigatório do TenantModel.
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
            models.UniqueConstraint(fields=["branch", "name"], name="unique_ingredient_by_branch"),
        ]
        indexes = [
            models.Index(fields=["branch", "is_active"]),
        ]

    def __str__(self):
        return self.name


class Recipe(TenantModel):
    product = models.OneToOneField(Product, related_name="recipe", on_delete=models.CASCADE)
    yield_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
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

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_ALL)
    is_active = models.BooleanField(default=True, db_index=True)
    available_from = models.TimeField(null=True, blank=True)
    available_until = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_menu_name_by_branch"),
        ]

    def __str__(self):
        return self.name


class MenuItem(TenantModel):
    menu = models.ForeignKey(Menu, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name="menu_items", on_delete=models.CASCADE)
    display_order = models.PositiveIntegerField(default=0)
    override_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order"]
        constraints = [
            models.UniqueConstraint(fields=["menu", "product"], name="unique_product_per_menu"),
        ]

    def __str__(self):
        return f"{self.menu} → {self.product}"

