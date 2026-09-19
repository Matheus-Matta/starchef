import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_role_is_account_admin'),
        ('inbound_nfe', '0001_initial'),
        ('restaurants', '0002_command_current_table_commandmovementlog'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='dfesyncstate',
            name='cnpj',
            field=models.CharField(blank=True, help_text='CNPJ utilizado na consulta DF-e.', max_length=14),
        ),
        migrations.AddField(
            model_name='dfesyncstate',
            name='environment',
            field=models.CharField(default='production', help_text='Ambiente: production ou homologation.', max_length=15),
        ),
        migrations.AddField(
            model_name='dfesyncstate',
            name='sync_error_count',
            field=models.PositiveIntegerField(default=0, help_text='Contagem de erros consecutivos de sincronização.'),
        ),
        migrations.AddField(
            model_name='inboundnfeitem',
            name='cest',
            field=models.CharField(blank=True, help_text='Código CEST do produto.', max_length=7),
        ),
        migrations.AddField(
            model_name='inboundnfeitem',
            name='ean_trib',
            field=models.CharField(blank=True, help_text='EAN tributário (cEANTrib).', max_length=14),
        ),
        migrations.AddField(
            model_name='inboundnfeitem',
            name='tax_data',
            field=models.JSONField(blank=True, default=dict, help_text='Dados tributários (ICMS, PIS, COFINS, IPI) extraídos do XML.'),
        ),
        migrations.CreateModel(
            name='DFeDistributionDocument',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('nsu', models.CharField(db_index=True, help_text='NSU do documento na SEFAZ.', max_length=15)),
                ('schema', models.CharField(blank=True, help_text='Atributo schema do docZip (ex: resNFe_v1.01.xsd).', max_length=100)),
                ('access_key', models.CharField(blank=True, db_index=True, help_text='Chave de acesso extraída do XML, quando disponível.', max_length=44)),
                ('document_type', models.CharField(choices=[('resNFe', 'Resumo NF-e'), ('procNFe', 'NF-e Completa'), ('resEvento', 'Resumo Evento'), ('procEventoNFe', 'Evento Completo'), ('unknown', 'Desconhecido')], default='unknown', help_text='Tipo do documento identificado pelo schema.', max_length=30)),
                ('xml', models.TextField(help_text='XML original descompactado. NUNCA apagar.')),
                ('received_at', models.DateTimeField(auto_now_add=True, help_text='Momento em que o documento foi recebido da SEFAZ.')),
                ('processed_at', models.DateTimeField(blank=True, help_text='Momento em que o processamento foi concluído.', null=True)),
                ('processing_status', models.CharField(choices=[('pending', 'Pendente'), ('ok', 'Processado'), ('error', 'Erro'), ('skipped', 'Ignorado')], default='pending', max_length=20)),
                ('processing_error', models.TextField(blank=True, help_text='Mensagem de erro do último processamento.')),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='accounts.account')),
                ('branch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='restaurants.branch')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('restaurant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='%(class)s_set', to='restaurants.restaurant')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Documento DF-e',
                'verbose_name_plural': 'Documentos DF-e',
                'ordering': ['nsu'],
            },
        ),
        migrations.AddConstraint(
            model_name='dfedistributiondocument',
            constraint=models.UniqueConstraint(fields=('account', 'nsu'), name='unique_dfe_doc_by_account_nsu'),
        ),
    ]
