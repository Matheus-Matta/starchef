from django.db import models

from apps.core.models import TenantModel


class ProductCategory(TenantModel):
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

    name = models.CharField(max_length=180, db_index=True)
    internal_code = models.CharField(max_length=60)
    description = models.TextField(blank=True)
    category = models.ForeignKey(ProductCategory, related_name="products", on_delete=models.PROTECT)
    image = models.ImageField(upload_to="products/", blank=True)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2)
    promotional_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    margin_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    product_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MEAL)
    average_preparation_time = models.PositiveIntegerField(default=15, help_text="Minutes")
    production_sector = models.CharField(max_length=20, choices=SECTOR_CHOICES, default=SECTOR_KITCHEN)
    controls_stock = models.BooleanField(default=False)
    allows_addons = models.BooleanField(default=True)
    allows_notes = models.BooleanField(default=True)
    available_for_table = models.BooleanField(default=True)
    available_for_counter = models.BooleanField(default=True)
    available_for_delivery = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["category__display_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "internal_code"], name="unique_product_code_by_branch"),
        ]
        indexes = [
            models.Index(fields=["branch", "is_active", "product_type"]),
            models.Index(fields=["branch", "production_sector"]),
        ]

    @property
    def current_price(self):
        return self.promotional_price or self.sale_price

    def __str__(self):
        return self.name


class ProductVariation(TenantModel):
    product = models.ForeignKey(Product, related_name="variations", on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    price_delta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_required = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "name"], name="unique_variation_by_product"),
        ]

    def __str__(self):
        return f"{self.product} - {self.name}"


class ProductAddon(TenantModel):
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

    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=12, choices=UNIT_CHOICES, default=UNIT_UNIT)
    average_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    minimum_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
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

