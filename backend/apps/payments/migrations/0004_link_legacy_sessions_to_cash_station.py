from django.db import migrations


def link_legacy_sessions(apps, schema_editor):
    CashRegister = apps.get_model("payments", "CashRegister")
    CashStation = apps.get_model("payments", "CashStation")

    restaurant_ids = CashRegister.objects.filter(cash_station__isnull=True).values_list(
        "restaurant_id", flat=True
    ).distinct()
    for restaurant_id in restaurant_ids:
        stations = CashStation.objects.filter(
            restaurant_id=restaurant_id,
            deleted_at__isnull=True,
            is_active=True,
        )
        if stations.count() == 1:
            CashRegister.objects.filter(
                restaurant_id=restaurant_id,
                cash_station__isnull=True,
            ).update(cash_station=stations.first())


class Migration(migrations.Migration):
    dependencies = [("payments", "0003_cashstation_cashregister_cash_station_and_more")]

    operations = [migrations.RunPython(link_legacy_sessions, migrations.RunPython.noop)]
