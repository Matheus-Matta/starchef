"""Sincroniza o catálogo canônico de permissões de negócio com o banco.

Idempotente: pode ser rodado quantas vezes quiser. Faz apenas upsert (nunca
remove permissões) para não órfãs vínculos já existentes em perfis/usuários.

    python manage.py sync_permissions
"""
from django.core.management.base import BaseCommand

from apps.accounts.models import Permission
from apps.accounts.permission_catalog import iter_permissions


def sync_permissions():
    """Upsert do catálogo. Retorna (criadas, atualizadas)."""
    created = updated = 0
    for code, defaults in iter_permissions():
        _obj, was_created = Permission.objects.update_or_create(code=code, defaults=defaults)
        if was_created:
            created += 1
        else:
            updated += 1
    return created, updated


class Command(BaseCommand):
    help = "Sincroniza o catálogo canônico de permissões de negócio (idempotente)."

    def handle(self, *args, **options):
        created, updated = sync_permissions()
        self.stdout.write(
            self.style.SUCCESS(f"Permissões sincronizadas: {created} criadas, {updated} atualizadas.")
        )
