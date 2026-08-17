from django.db import migrations


def unify_payment_receipts(apps, schema_editor):
    PrintJob = apps.get_model("printers", "PrintJob")
    PrintJob.objects.filter(job_type="payment_receipt").update(job_type="receipt")


class Migration(migrations.Migration):
    dependencies = [("printers", "0001_initial")]

    operations = [migrations.RunPython(unify_payment_receipts, migrations.RunPython.noop)]
