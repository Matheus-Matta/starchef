from django.db import models

from apps.core.models import TenantBaseModel
from apps.restaurants.models import Branch, Restaurant


class KdsStation(TenantBaseModel):
    name = models.CharField(max_length=100)
    restaurant = models.ForeignKey(Restaurant, related_name="kds_stations", on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, null=True, blank=True, related_name="kds_stations", on_delete=models.SET_NULL)
    sla_minutes = models.PositiveIntegerField(default=15)
    sectors = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
