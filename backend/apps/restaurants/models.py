from django.db import models

from apps.core.models import TenantBaseModel, TenantModel


class Restaurant(TenantBaseModel):
    legal_name = models.CharField(max_length=180)
    trade_name = models.CharField(max_length=180, db_index=True)
    # CNPJ opcional: nulos não conflitam no índice único (vários restaurantes
    # podem ficar sem CNPJ). Vazio é normalizado para null no serializer.
    cnpj = models.CharField(max_length=18, unique=True, null=True, blank=True)
    state_registration = models.CharField(max_length=40, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=2, blank=True)
    zip_code = models.CharField(max_length=16, blank=True)
    logo = models.ImageField(upload_to="restaurants/logos/", blank=True)
    default_service_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    operational_settings = models.JSONField(default=dict, blank=True)
    fiscal_settings = models.JSONField(default=dict, blank=True)
    print_settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["trade_name"]

    def __str__(self):
        return self.trade_name


class Branch(TenantBaseModel):
    STOCK_DEDUCTION_PAYMENT = "payment"
    STOCK_DEDUCTION_KITCHEN = "kitchen"

    STOCK_DEDUCTION_CHOICES = [
        (STOCK_DEDUCTION_PAYMENT, "On payment"),
        (STOCK_DEDUCTION_KITCHEN, "On kitchen send"),
    ]

    restaurant = models.ForeignKey(Restaurant, related_name="branches", on_delete=models.PROTECT)
    name = models.CharField(max_length=160)
    cnpj = models.CharField(max_length=18, blank=True)
    state_registration = models.CharField(max_length=40, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=2, blank=True)
    zip_code = models.CharField(max_length=16, blank=True)
    opening_hours = models.JSONField(default=dict, blank=True)
    default_service_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    require_open_cash_register = models.BooleanField(default=True)
    stock_deduction_timing = models.CharField(
        max_length=20,
        choices=STOCK_DEDUCTION_CHOICES,
        default=STOCK_DEDUCTION_PAYMENT,
    )
    print_settings = models.JSONField(default=dict, blank=True)
    fiscal_settings = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["restaurant__trade_name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["restaurant", "name"], name="unique_branch_name_by_restaurant"),
        ]
        indexes = [
            models.Index(fields=["restaurant", "is_active"]),
        ]

    def __str__(self):
        return f"{self.restaurant} - {self.name}"


class TableSector(TenantModel):
    name = models.CharField(max_length=80)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["display_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_table_sector_by_branch"),
        ]

    def __str__(self):
        return self.name


class Table(TenantModel):
    STATUS_FREE = "free"
    STATUS_OCCUPIED = "occupied"
    STATUS_RESERVED = "reserved"
    STATUS_CLEANING = "cleaning"

    STATUS_CHOICES = [
        (STATUS_FREE, "Free"),
        (STATUS_OCCUPIED, "Occupied"),
        (STATUS_RESERVED, "Reserved"),
        (STATUS_CLEANING, "Waiting cleaning"),
    ]

    sector = models.ForeignKey(TableSector, related_name="tables", on_delete=models.PROTECT)
    number = models.CharField(max_length=20)
    capacity = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_FREE, db_index=True)
    current_order_id = models.UUIDField(null=True, blank=True, db_index=True)
    joined_to = models.ForeignKey("self", null=True, blank=True, related_name="joined_tables", on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["sector__display_order", "number"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "number"], name="unique_table_number_by_branch"),
        ]
        indexes = [
            models.Index(fields=["branch", "status"]),
        ]

    def __str__(self):
        return f"Table {self.number}"


class Command(TenantModel):
    code = models.CharField(max_length=40)
    customer_name = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=24, default="open", db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "code"], name="unique_command_code_by_branch"),
        ]

    def __str__(self):
        return self.code


class DeliveryZone(TenantModel):
    name = models.CharField(max_length=120)
    min_radius_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    max_radius_km = models.DecimalField(max_digits=8, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estimated_minutes = models.PositiveIntegerField(default=45)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["min_radius_km"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_delivery_zone_by_branch"),
        ]

    def __str__(self):
        return f"{self.name} (até {self.max_radius_km}km)"


class Deliveryman(TenantModel):
    VEHICLE_BIKE = "bike"
    VEHICLE_MOTORCYCLE = "motorcycle"
    VEHICLE_CAR = "car"
    VEHICLE_FOOT = "foot"

    VEHICLE_CHOICES = [
        (VEHICLE_BIKE, "Bike"),
        (VEHICLE_MOTORCYCLE, "Motorcycle"),
        (VEHICLE_CAR, "Car"),
        (VEHICLE_FOOT, "On foot"),
    ]

    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32, blank=True)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_CHOICES, default=VEHICLE_MOTORCYCLE)
    vehicle_plate = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_deliveryman_by_branch"),
        ]

    def __str__(self):
        return self.name
