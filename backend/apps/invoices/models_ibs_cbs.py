"""Os campos de IBS/CBS: no perfil fiscal (a regra) e no item da nota (o retrato).

Um mixin só para os dois, porque o item COPIA a regra do perfil no momento da
venda (`services.rebuild_invoice_items`) — corrigir o perfil depois não mexe
numa nota emitida. Dois conjuntos de campos escritos à mão divergiriam no
primeiro campo novo.

Alíquota NÃO mora aqui: ela vem do ano da emissão (`ibs_cbs.ALIQUOTAS`).
"""
from django.db import models


class IbsCbsCampos(models.Model):
    ibs_cbs_cst = models.CharField(
        max_length=3, blank=True, help_text="CST do IBS/CBS (ex.: 000). Um só para os dois tributos."
    )
    ibs_cbs_cclass_trib = models.CharField(
        max_length=6, blank=True, help_text="Classificação tributária do IBS/CBS (cClassTrib, ex.: 000001)."
    )
    ibs_cbs_reducao = models.DecimalField(
        max_digits=7, decimal_places=4, default=0,
        help_text="Redução de alíquota (pRedAliq) em %. Só nos CST 200 e 515.",
    )
    ibs_cbs_diferimento = models.DecimalField(
        max_digits=7, decimal_places=4, default=0,
        help_text="Diferimento (pDif) em %. Só nos CST 510 e 515.",
    )

    class Meta:
        abstract = True


CAMPOS = ("ibs_cbs_cst", "ibs_cbs_cclass_trib", "ibs_cbs_reducao", "ibs_cbs_diferimento")


def retrato(perfil):
    """A regra do perfil copiada para o item da nota; sem perfil, os padrões."""
    return {campo: getattr(perfil, campo) for campo in CAMPOS} if perfil else {}
