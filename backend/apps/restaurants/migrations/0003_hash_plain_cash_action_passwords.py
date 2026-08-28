from django.contrib.auth.hashers import PBKDF2PasswordHasher, identify_hasher
from django.db import migrations


def hash_plain_cash_action_passwords(apps, schema_editor):
    Restaurant = apps.get_model("restaurants", "Restaurant")
    # O manager tenant depende do contexto da request e ficaria vazio durante
    # `migrate`; o base manager precisa percorrer todas as contas.
    for restaurant in Restaurant._base_manager.exclude(cash_action_password="").iterator():
        encoded = restaurant.cash_action_password
        try:
            decoded = PBKDF2PasswordHasher().decode(encoded)
            already_encoded = bool(decoded["salt"] and decoded["hash"] and decoded["iterations"] > 0)
        except (AssertionError, TypeError, ValueError):
            try:
                identify_hasher(encoded)
                already_encoded = True
            except ValueError:
                already_encoded = False
        if already_encoded:
            continue
        hasher = PBKDF2PasswordHasher()
        restaurant.cash_action_password = hasher.encode(encoded, hasher.salt())
        restaurant.save(update_fields=["cash_action_password"])


class Migration(migrations.Migration):
    dependencies = [("restaurants", "0002_command_current_table_commandmovementlog")]

    operations = [
        migrations.RunPython(hash_plain_cash_action_passwords, migrations.RunPython.noop),
    ]
