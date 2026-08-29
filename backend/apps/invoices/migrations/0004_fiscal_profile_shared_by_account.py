"""O perfil fiscal deixa de ser da filial e passa a ser um cadastro da CONTA.

Antes ele nascia preso a um restaurante/filial (constraint por filial), o que
obrigava a recadastrar o mesmo "Bebida" em cada unidade. Agora e reutilizavel
como as categorias do cardapio: restaurante/filial ficam nulos e o nome e unico
na conta. Quem escolhe o perfil continua sendo o produto (relacao 1:N).

A migration de dados nao reaponta produto nenhum: quando dois perfis de filiais
diferentes tem o mesmo nome, o mais antigo mantem o nome e os seguintes ganham
um sufixo — nada de fundir aliquotas silenciosamente.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def unscope_and_dedupe_names(apps, schema_editor):
    FiscalProfile = apps.get_model("invoices", "FiscalProfile")

    # Inclui os soft-deleted de proposito: eles continuam ocupando o nome na
    # constraint, entao precisam entrar na contagem de colisoes.
    taken = set()
    for profile in FiscalProfile.objects.order_by("account_id", "created_at", "id").iterator():
        base = (profile.name or "").strip() or "Perfil fiscal"
        candidate = base
        suffix = 1
        while (profile.account_id, candidate) in taken:
            suffix += 1
            candidate = f"{base} ({suffix})"
        taken.add((profile.account_id, candidate))

        profile.name = candidate
        # Passa a valer para a conta inteira.
        profile.restaurant_id = None
        profile.branch_id = None
        profile.save()


def noop(apps, schema_editor):
    """Sem volta: o vinculo original de filial nao e recuperavel depois de nulo."""


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_seed_system_roles'),
        ('invoices', '0003_fiscalconfig_focus_certificate_base64_and_more'),
        ('restaurants', '0003_hash_plain_cash_action_passwords'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='fiscalprofile',
            options={'ordering': ['name']},
        ),
        migrations.RemoveConstraint(
            model_name='fiscalprofile',
            name='unique_fiscal_profile_by_branch',
        ),
        migrations.AlterField(
            model_name='fiscalprofile',
            name='is_default',
            field=models.BooleanField(default=False, help_text='Marca o perfil sugerido no cadastro de produtos.'),
        ),
        migrations.AlterField(
            model_name='fiscalprofile',
            name='restaurant',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='restaurants.restaurant'),
        ),
        # Desescopa e resolve nomes repetidos ANTES de a nova constraint entrar.
        migrations.RunPython(unscope_and_dedupe_names, noop),
        migrations.AddConstraint(
            model_name='fiscalprofile',
            constraint=models.UniqueConstraint(fields=('account', 'name'), name='unique_fiscal_profile_by_account'),
        ),
    ]
