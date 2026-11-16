"""Escritas coletivas de patrimônio sem perder sinais de sincronização."""
from django.db import transaction

from apps.assets.models import Asset, AssetLocationHistory
from apps.core.lote import atualizar_em_lote, criar_em_lote


def _travados(queryset, ids):
    """Trava só as linhas do PRÓPRIO ativo (`of=("self",)`).

    O queryset da view traz `select_related` de FKs opcionais (local,
    responsável, nota); sem `of`, o Postgres recusa o `FOR UPDATE` no lado
    nulo do LEFT JOIN e a ação em lote respondia 500 — só em produção, porque
    o SQLite ignora o `FOR UPDATE`.
    """
    return list(queryset.select_for_update(of=("self",)).filter(id__in=ids).order_by("pk"))


def update_asset_status(queryset, *, ids, new_status):
    with transaction.atomic():
        assets = _travados(queryset, ids)
        for asset in assets:
            asset.status = new_status
        atualizar_em_lote(Asset, assets, ["status", "updated_at"])
    return assets


def transfer_assets(queryset, *, ids, to_location, user, reason, notes):
    with transaction.atomic():
        assets = _travados(queryset, ids)
        histories = []
        for asset in assets:
            histories.append(
                AssetLocationHistory(
                    account=asset.account,
                    restaurant=asset.restaurant,
                    branch=asset.branch,
                    asset=asset,
                    from_location=asset.location,
                    to_location=to_location,
                    moved_by=user,
                    reason=reason,
                    notes=notes,
                )
            )
            asset.location = to_location
        criar_em_lote(AssetLocationHistory, histories)
        atualizar_em_lote(Asset, assets, ["location", "updated_at"])
    return assets
