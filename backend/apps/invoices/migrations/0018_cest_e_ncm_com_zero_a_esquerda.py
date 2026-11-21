"""Os perfis fiscais gravados com CEST/NCM sem o zero do Excel ("300504").

Produção, 21/11/2026: "CEST ... The value '300504' is not accepted by the
pattern '[0-9]{7}'". A montagem da nota já completa (`codigos_fiscais.py`);
esta migração acerta o cadastro, como a 0017 fez com o CST. Roda em cada
servidor (nuvem e loja), por isso não gera evento de sincronização.
"""
from django.db import migrations

TAMANHOS = {"ncm": 8, "cest": 7}


def completar(apps, schema_editor):
    FiscalProfile = apps.get_model("invoices", "FiscalProfile")
    for perfil in FiscalProfile._base_manager.all().only("pk", *TAMANHOS):
        mudou = {}
        for campo, tamanho in TAMANHOS.items():
            valor = str(getattr(perfil, campo) or "").strip()
            if valor.isdigit() and len(valor) < tamanho:
                mudou[campo] = valor.zfill(tamanho)
        if mudou:
            FiscalProfile._base_manager.filter(pk=perfil.pk).update(**mudou)


class Migration(migrations.Migration):
    dependencies = [("invoices", "0017_cst_com_zero_a_esquerda")]

    operations = [migrations.RunPython(completar, migrations.RunPython.noop)]
