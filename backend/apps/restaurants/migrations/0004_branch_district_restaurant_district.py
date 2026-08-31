from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("restaurants", "0003_hash_plain_cash_action_passwords")]

    operations = [
        migrations.AddField(
            model_name="branch",
            name="district",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="restaurant",
            name="district",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
