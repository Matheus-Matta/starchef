import pytest
from django.db.models.signals import post_save

from apps.assets.models import Asset, AssetLocationHistory
from apps.menu.models import Product
from apps.stock.models import StockLocation


pytestmark = pytest.mark.django_db


def _cenario(account, restaurant, branch):
    produto = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Equipamento",
        internal_code="EQUIP-1",
        item_type=Product.ITEM_EQUIPMENT,
        tracking_mode=Product.TRACKING_SERIALIZED,
    )
    origem = StockLocation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Origem"
    )
    destino = StockLocation.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Destino"
    )
    ativos = [
        Asset.objects.create(
            account=account,
            restaurant=restaurant,
            branch=branch,
            product=produto,
            location=origem,
        )
        for _ in range(2)
    ]
    return origem, destino, ativos


def test_status_em_lote_dispara_sinal_para_sincronizacao(
    admin_client, account, restaurant, branch
):
    """A escrita coletiva não pode deixar a outra instalação com status antigo."""
    _, _, ativos = _cenario(account, restaurant, branch)
    alterados = []

    def registrar(sender, instance, created, **kwargs):
        if not created:
            alterados.append(instance.pk)

    post_save.connect(registrar, sender=Asset, weak=False)
    try:
        response = admin_client.post(
            "/api/v1/assets/bulk-update-status/",
            {"ids": [str(item.pk) for item in ativos], "status": Asset.STATUS_IN_MAINTENANCE},
            format="json",
        )
    finally:
        post_save.disconnect(registrar, sender=Asset)

    assert response.status_code == 200, response.content
    assert set(alterados) == {item.pk for item in ativos}


def test_transferencia_em_lote_dispara_sinais_de_ativo_e_historico(
    admin_client, account, restaurant, branch
):
    """A transferência coletiva precisa sincronizar ativos e seus históricos."""
    _, destino, ativos = _cenario(account, restaurant, branch)
    ativos_alterados = []
    historicos_criados = []

    def registrar_ativo(sender, instance, created, **kwargs):
        if not created:
            ativos_alterados.append(instance.pk)

    def registrar_historico(sender, instance, created, **kwargs):
        if created:
            historicos_criados.append(instance.asset_id)

    post_save.connect(registrar_ativo, sender=Asset, weak=False)
    post_save.connect(registrar_historico, sender=AssetLocationHistory, weak=False)
    try:
        response = admin_client.post(
            "/api/v1/assets/bulk-transfer/",
            {"ids": [str(item.pk) for item in ativos], "to_location": str(destino.pk)},
            format="json",
        )
    finally:
        post_save.disconnect(registrar_ativo, sender=Asset)
        post_save.disconnect(registrar_historico, sender=AssetLocationHistory)

    assert response.status_code == 200, response.content
    ids = {item.pk for item in ativos}
    assert set(ativos_alterados) == ids
    assert set(historicos_criados) == ids
