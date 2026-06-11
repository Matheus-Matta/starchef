from django.db import models

from apps.core.models import TenantModel


class Customer(TenantModel):
    name = models.CharField(max_length=180)
    phone = models.CharField(max_length=32, db_index=True)
    email = models.EmailField(blank=True)
    document = models.CharField(max_length=20, blank=True)
    internal_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["branch", "phone"]),
            models.Index(fields=["restaurant", "name"]),
        ]

    def __str__(self):
        return self.name


class CustomerAddress(TenantModel):
    customer = models.ForeignKey(Customer, related_name="addresses", on_delete=models.CASCADE)
    label = models.CharField(max_length=80, default="Principal")
    street = models.CharField(max_length=180)
    number = models.CharField(max_length=20, blank=True)
    complement = models.CharField(max_length=120, blank=True)
    district = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    zip_code = models.CharField(max_length=16, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["customer", "-is_default", "label"]

    def __str__(self):
        return f"{self.customer} - {self.label}"

