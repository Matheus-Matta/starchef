"""Remove UserProfile.profile_type e torna UserProfile.role obrigatorio.

Perfil de acesso (Role) passa a ser a UNICA fonte de controle de acesso do
usuario — o campo profile_type era redundante com ele (ver
0006_backfill_userprofile_role, que ja preencheu role em todo profile
existente antes desta migration rodar).
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_backfill_userprofile_role"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="userprofile",
            name="accounts_us_account_50749a_idx",
        ),
        migrations.RemoveIndex(
            model_name="userprofile",
            name="accounts_us_restaur_6e9730_idx",
        ),
        migrations.RemoveField(
            model_name="userprofile",
            name="profile_type",
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="user_profiles",
                to="accounts.role",
            ),
        ),
        migrations.AddIndex(
            model_name="userprofile",
            index=models.Index(fields=["account", "role"], name="accounts_us_account_role_idx"),
        ),
        migrations.AddIndex(
            model_name="userprofile",
            index=models.Index(fields=["restaurant", "branch", "role"], name="accounts_us_rbr_role_idx"),
        ),
    ]
