import uuid

import django.db.models.deletion
from django.db import migrations, models


def seed_cosmos_configs(apps, schema_editor):
    Account = apps.get_model("accounts", "Account")
    CosmosConfig = apps.get_model("accounts", "CosmosConfig")
    CosmosConfig.objects.bulk_create(
        [CosmosConfig(account_id=account_id) for account_id in Account.objects.values_list("id", flat=True)],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_remove_profile_type_require_role"),
    ]

    operations = [
        migrations.CreateModel(
            name="CosmosConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("api_token", models.CharField(blank=True, max_length=255)),
                (
                    "user_agent",
                    models.CharField(
                        blank=True,
                        help_text="User-Agent fornecido pela Cosmos junto com o token da API.",
                        max_length=255,
                    ),
                ),
                ("timeout_seconds", models.PositiveSmallIntegerField(default=10)),
                ("is_active", models.BooleanField(default=False)),
                (
                    "account",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cosmos_config",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "verbose_name": "configuracao Cosmos",
                "verbose_name_plural": "configuracoes Cosmos",
            },
        ),
        migrations.RunPython(seed_cosmos_configs, migrations.RunPython.noop),
    ]
