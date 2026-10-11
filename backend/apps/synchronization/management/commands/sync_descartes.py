"""Lista ou exporta o que este nó ignorou (`SyncDiscard`).

    python manage.py sync_descartes                         # os 50 mais recentes
    python manage.py sync_descartes --motivo reenvio --tipo payment
    python manage.py sync_descartes --id <uuid> --json      # tudo de um registro, para recuperar
"""
import json

from django.core.management.base import BaseCommand

from apps.synchronization.models import SyncDiscard


class Command(BaseCommand):
    help = "Lista ou exporta o histórico do que este nó ignorou."

    def add_arguments(self, parser):
        parser.add_argument("--motivo", choices=[m for m, _ in SyncDiscard.MOTIVO_CHOICES])
        parser.add_argument("--origem", choices=[o for o, _ in SyncDiscard.ORIGEM_CHOICES])
        parser.add_argument("--tipo", help="entity_type, ex.: payment, order_item")
        parser.add_argument("--id", help="entity_id do registro")
        parser.add_argument("--limite", type=int, default=50)
        parser.add_argument("--json", action="store_true", help="exporta com os dados completos")

    def handle(self, *args, **opcoes):
        filtro = {campo: opcoes[chave] for chave, campo in (
            ("motivo", "motivo"), ("origem", "origem"), ("tipo", "entity_type"), ("id", "entity_id"),
        ) if opcoes.get(chave)}
        descartes = SyncDiscard.objects.filter(**filtro)[: opcoes["limite"]]
        if opcoes["json"]:
            self.stdout.write(json.dumps([{
                "id": str(d.pk), "quando": d.created_at.isoformat(), "motivo": d.motivo,
                "origem": d.origem, "entity_type": d.entity_type, "entity_id": d.entity_id,
                "versao_recebida": d.versao_recebida, "versao_local": d.versao_local,
                "evento": str(d.event_id or ""), "usuario": d.usuario_id, "dados": d.dados,
            } for d in descartes], ensure_ascii=False, indent=1))
            return
        for d in descartes:
            self.stdout.write(f"{d.created_at:%d/%m %H:%M:%S}  {d.motivo:<24} {d.origem:<4} "
                              f"{d.entity_type}/{d.entity_id}")
