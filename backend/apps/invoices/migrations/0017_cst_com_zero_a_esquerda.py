"""Os perfis fiscais gravados sem o zero do CST ("4" em vez de "04").

Produção, 20/11/2026: "ACBrLib: Valor string inválido para TCSTPIS: 4". A
planilha de perfis passou pelo Excel antes da importação, que só completa o
zero desde a 3.1.19 (`codigos_fiscais.py`). O que já estava gravado segue
emitindo pela montagem da nota, mas o cadastro mostrava "4" e qualquer outro
leitor do perfil herdava o código errado.

Corrige no banco de CADA servidor (nuvem e loja rodam a mesma migração), por
isso não precisa gerar evento de sincronização. Só perfis: item de nota
autorizada é o retrato do que foi à SEFAZ e não se reescreve.
"""
from django.db import migrations

TAMANHOS = {"cst_icms": 2, "csosn": 3, "pis_cst": 2, "cofins_cst": 2,
            "ibs_cbs_cst": 3, "ibs_cbs_cclass_trib": 6}


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
    dependencies = [("invoices", "0016_ibs_cbs_reforma_tributaria")]

    operations = [migrations.RunPython(completar, migrations.RunPython.noop)]
