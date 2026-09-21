import base64

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


pytestmark = pytest.mark.django_db(transaction=True)

MIGRATION_BEFORE = ("invoices", "0009_merge_20260919_1834")
MIGRATION_AFTER = ("invoices", "0010_unifica_certificado_focus")


def test_migration_moves_focus_a1_to_canonical_fields(
    account, restaurant, branch
):
    """O deploy não pode apagar o A1 que antes existia só nos campos Focus."""
    executor = MigrationExecutor(connection)
    executor.migrate([MIGRATION_BEFORE])
    old_apps = executor.loader.project_state([MIGRATION_BEFORE]).apps
    OldFiscalConfig = old_apps.get_model("invoices", "FiscalConfig")
    certificate = b"certificado-a1-legado"
    config = OldFiscalConfig.objects.create(
        account_id=account.id,
        restaurant_id=restaurant.id,
        branch_id=branch.id,
        focus_certificate_base64=base64.b64encode(certificate).decode(),
        focus_certificate_password="senha-legada",
    )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate([MIGRATION_AFTER])
        new_apps = executor.loader.project_state([MIGRATION_AFTER]).apps
        migrated = new_apps.get_model("invoices", "FiscalConfig").objects.get(pk=config.pk)

        assert migrated.certificate_password == "senha-legada"
        assert migrated.certificate_ref == migrated.certificate_file.name
        migrated.certificate_file.open("rb")
        try:
            assert migrated.certificate_file.read() == certificate
        finally:
            migrated.certificate_file.close()
    finally:
        MigrationExecutor(connection).migrate([MIGRATION_AFTER])
