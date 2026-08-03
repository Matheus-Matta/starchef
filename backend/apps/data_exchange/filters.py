from django.core.exceptions import FieldDoesNotExist
from django.db import models
from rest_framework.filters import BaseFilterBackend


class AdvancedFieldFilterBackend(BaseFilterBackend):
    """Safe, reusable filtering for fields exposed by a resource serializer."""

    prefix = "filter__"
    blocked_fields = {
        "password",
        "token",
        "secret",
        "api_key",
        "access_token",
        "refresh_token",
    }

    def filter_queryset(self, request, queryset, view):
        requested = {
            key.removeprefix(self.prefix): value
            for key, value in request.query_params.items()
            if key.startswith(self.prefix) and value != ""
        }
        if not requested:
            return queryset

        serializer = view.get_serializer()
        exposed = {
            name
            for name, field in serializer.fields.items()
            if not field.write_only and name not in self.blocked_fields
        }
        filters = {}
        for name, value in requested.items():
            if name not in exposed or "__" in name:
                continue
            try:
                model_field = queryset.model._meta.get_field(name)
            except FieldDoesNotExist:
                continue
            if not model_field.concrete and not model_field.many_to_many:
                continue
            lookup = name
            if isinstance(model_field, (models.CharField, models.TextField)):
                lookup = f"{name}__icontains"
            filters[lookup] = value
        return queryset.filter(**filters).distinct() if filters else queryset
