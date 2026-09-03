from django.db import models

from apps.core.models import TenantModel


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

    ITEM_INGREDIENT = "INGREDIENT"
    ITEM_RESALE = "RESALE_PRODUCT"
    ITEM_CONSUMABLE = "CONSUMABLE"
    ITEM_REUSABLE = "REUSABLE_MATERIAL"
    ITEM_EQUIPMENT = "EQUIPMENT"
    ITEM_FIXED_ASSET = "FIXED_ASSET"
    ITEM_PACKAGING = "PACKAGING"
    ITEM_SERVICE = "SERVICE"
    ITEM_OTHER = "OTHER"

    ITEM_TYPE_CHOICES = [
        (ITEM_INGREDIENT, "Insumo / Ingrediente"),
        (ITEM_RESALE, "Mercadoria p/ Revenda"),
        (ITEM_CONSUMABLE, "Material de Consumo"),
        (ITEM_REUSABLE, "Material Reutilizável (Utensílio)"),
        (ITEM_EQUIPMENT, "Equipamento Operacional"),
        (ITEM_FIXED_ASSET, "Ativo Fixo / Patrimônio"),
        (ITEM_PACKAGING, "Embalagem"),
        (ITEM_SERVICE, "Serviço"),
        (ITEM_OTHER, "Outro"),
    ]

    TRACKING_QUANTITY = "QUANTITY"
    TRACKING_LOT = "LOT"
    TRACKING_SERIALIZED = "SERIALIZED"

    TRACKING_MODE_CHOICES = [
        (TRACKING_QUANTITY, "Por Quantidade"),
        (TRACKING_LOT, "Por Lote e Validade"),
        (TRACKING_SERIALIZED, "Serializado (Patrimônio)"),
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
    item_type = models.CharField(
        max_length=30,
        choices=ITEM_TYPE_CHOICES,
        default=ITEM_RESALE,
        db_index=True,
        help_text="Classificação de finalidade do item."
    )
    tracking_mode = models.CharField(
        max_length=20,
        choices=TRACKING_MODE_CHOICES,
        default=TRACKING_QUANTITY,
        db_index=True,
        help_text="Tipo de rastreamento físico (quantidade, lote ou serializado)."
    )
    restaurants = models.ManyToManyField(
        "restaurants.Restaurant",
        related_name="available_products",
        blank=True,
        help_text="Restaurantes da conta que podem comercializar este produto.",
    )
    internal_code = models.CharField(max_length=60)
    gtin = models.CharField(
        max_length=14,
        blank=True,
        db_index=True,
        help_text="GTIN/EAN/UPC do produto, somente dígitos."
    )
    brand = models.CharField(max_length=120, blank=True, help_text="Marca do produto/fabricante.")
    model = models.CharField(max_length=120, blank=True, help_text="Modelo ou especificação.")
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        ProductCategory,
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )
    image = models.ImageField(upload_to="products/", blank=True)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Por unidade, ou por kg quando pricing_unit=kg.")
    promotional_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    pricing_unit = models.CharField(max_length=8, choices=PRICING_CHOICES, default=PRICING_UNIT)
    stock_unit = models.CharField(max_length=12, default="UN", help_text="Unidade padrão no estoque (ex: UN, KG, L, G, ML).")
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_average_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0, help_text="Custo médio ponderado atual.")
    last_purchase_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0, help_text="Último custo unitário de compra.")
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
    controls_stock = models.BooleanField(default=True, help_text="Se o produto movimenta estoque físico.")
    minimum_stock = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, help_text="Estoque mínimo de segurança.")
    maximum_stock = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, help_text="Estoque máximo desejado.")
    requires_expiration_control = models.BooleanField(default=False, help_text="Exige data de validade na entrada.")
    requires_lot_control = models.BooleanField(default=False, help_text="Exige número de lote na entrada.")
    requires_serial_number = models.BooleanField(default=False, help_text="Exige número de série individual.")
    requires_maintenance = models.BooleanField(default=False, help_text="Exige plano de manutenção periódica.")
    requires_cleaning_schedule = models.BooleanField(default=False, help_text="Exige rotina periódica de limpeza/higienização.")
    allow_negative_stock = models.BooleanField(default=False, help_text="Permite estoque negativo (padrão False).")
    default_useful_life_months = models.PositiveIntegerField(null=True, blank=True, help_text="Vida útil estimada em meses.")
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
            models.UniqueConstraint(
                fields=["branch", "gtin"],
                condition=~models.Q(gtin=""),
                name="unique_product_gtin_by_branch",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "is_active", "product_type"]),
            models.Index(fields=["branch", "production_sector"]),
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


class ProductUnitConversion(TenantModel):
    product = models.ForeignKey(
        Product,
        related_name="unit_conversions",
        on_delete=models.CASCADE
    )
    source_unit = models.CharField(max_length=12, help_text="Unidade de compra / fiscal (ex: CX, FD, BD, LT)")
    target_unit = models.CharField(max_length=12, help_text="Unidade interna de estoque (ex: UN, KG, L, G, ML)")
    factor = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=1,
        help_text="Multiplicador de conversão: 1 source_unit = factor * target_unit"
    )
    supplier_cnpj = models.CharField(
        max_length=14,
        blank=True,
        help_text="CNPJ do fornecedor se for regra específica."
    )
    supplier_product_code = models.CharField(
        max_length=60,
        blank=True,
        help_text="Código do produto no fornecedor."
    )

    class Meta:
        verbose_name = "Conversão de Unidade de Produto"
        verbose_name_plural = "Conversões de Unidades de Produtos"
        constraints = [
            models.UniqueConstraint(
                fields=["account", "product", "source_unit", "supplier_cnpj", "supplier_product_code"],
                name="unique_unit_conversion_rule"
            )
        ]

    def __str__(self):
        return f"{self.product.name}: 1 {self.source_unit} = {self.factor} {self.target_unit}"


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
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_addon_by_branch"),
        ]

    def __str__(self):
        return self.name


class Ingredient(TenantModel):
    UNIT_UNIT = "unit"
    UNIT_KG = "kg"
    UNIT_G = "g"
    UNIT_L = "l"
    UNIT_ML = "ml"

    UNIT_CHOICES = [
        (UNIT_UNIT, "Unit"),
        (UNIT_KG, "Kg"),
        (UNIT_G, "g"),
        (UNIT_L, "L"),
        (UNIT_ML, "ml"),
    ]

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

