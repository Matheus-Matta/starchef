from django.db import migrations

# Torna o email do usuario unico de forma case-insensitive (casa com o login
# por email__iexact). Indice parcial: emails vazios continuam permitidos, pois
# email e opcional (blank/null) no auth.User padrao.
CREATE_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uniq_auth_user_email_ci "
    "ON auth_user (LOWER(email)) "
    "WHERE email IS NOT NULL AND email <> '';"
)
DROP_INDEX = "DROP INDEX IF EXISTS uniq_auth_user_email_ci;"


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_initial"),
        ("auth", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_INDEX, reverse_sql=DROP_INDEX),
    ]
