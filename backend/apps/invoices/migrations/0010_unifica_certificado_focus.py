import base64

from django.core.files.base import ContentFile
from django.db import migrations
from django.db.models import Q


def usar_certificado_canonico(apps, schema_editor):
    FiscalConfig = apps.get_model("invoices", "FiscalConfig")
    antigos = FiscalConfig.objects.filter(
        Q(focus_certificate_base64__gt="") | Q(focus_certificate_password__gt="")
    )
    for config in antigos.iterator():
        changed = []
        if not config.certificate_file and config.focus_certificate_base64:
            encoded = "".join(config.focus_certificate_base64.split())
            content = base64.b64decode(encoded, validate=True)
            config.certificate_file.save(
                f"focus-{config.pk}.pfx",
                ContentFile(content),
                save=False,
            )
            config.certificate_ref = config.certificate_file.name
            changed.extend(["certificate_file", "certificate_ref"])
        if not config.certificate_password and config.focus_certificate_password:
            config.certificate_password = config.focus_certificate_password
            changed.append("certificate_password")
        if changed:
            config.save(update_fields=changed)


def restaurar_campos_legados(apps, schema_editor):
    FiscalConfig = apps.get_model("invoices", "FiscalConfig")
    for config in FiscalConfig.objects.exclude(certificate_file="").iterator():
        config.certificate_file.open("rb")
        try:
            content = config.certificate_file.read()
        finally:
            config.certificate_file.close()
        config.focus_certificate_base64 = base64.b64encode(content).decode()
        config.focus_certificate_password = config.certificate_password
        config.save(update_fields=["focus_certificate_base64", "focus_certificate_password"])


class Migration(migrations.Migration):
    dependencies = [("invoices", "0009_merge_20260919_1834")]

    operations = [
        migrations.RunPython(usar_certificado_canonico, restaurar_campos_legados),
        migrations.RemoveField(model_name="fiscalconfig", name="focus_certificate_base64"),
        migrations.RemoveField(model_name="fiscalconfig", name="focus_certificate_password"),
    ]
