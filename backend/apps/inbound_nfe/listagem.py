"""Listagem de NF-e de entrada: contagens na mesma consulta da página."""
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery
from django.db.models.functions import Coalesce

from apps.inbound_nfe.models import InboundNFeItem, NFeManifestation


def com_contagens(qs):
    """Contagens de itens e a última manifestação, na MESMA consulta da página.

    O serializer fazia 4 COUNT + 1 SELECT por nota: 50 notas, ~250 consultas.
    Subconsulta (e não `Count("items")`) porque a busca por `items__...` já
    junta itens — o JOIN reaproveitado contaria só os itens que casaram.
    """
    def contar(**filtro):
        sub = (InboundNFeItem.all_objects.filter(invoice=OuterRef("pk"), **filtro)
               .order_by().values("invoice").annotate(n=Count("pk")).values("n"))
        return Coalesce(Subquery(sub, output_field=IntegerField()), 0)

    return qs.annotate(
        _n_itens=contar(),
        _n_ignorados=contar(is_ignored=True),
        _n_sem_vinculo=contar(is_ignored=False, ingredient__isnull=True, product__isnull=True),
    ).prefetch_related(Prefetch(
        "manifestations", queryset=NFeManifestation.all_objects.order_by("-created_at"), to_attr="_manifestacoes",
    ))
