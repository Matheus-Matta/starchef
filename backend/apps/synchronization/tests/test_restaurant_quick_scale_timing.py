from apps.synchronization.catalog import registry
from apps.synchronization.services.serialization import serialize

import pytest

pytestmark = pytest.mark.django_db


def test_restaurant_quick_scale_timing_is_in_sync_payload(restaurant):
    """Os terminais locais precisam receber os dois tempos configurados na nuvem."""
    restaurant.quick_scale_command_timeout_seconds = 77
    restaurant.quick_scale_stability_seconds = 4
    restaurant.save(
        update_fields=[
            "quick_scale_command_timeout_seconds",
            "quick_scale_stability_seconds",
        ]
    )

    payload = serialize(restaurant, registry.require("restaurant"))

    assert payload["quick_scale_command_timeout_seconds"] == 77
    assert payload["quick_scale_stability_seconds"] == 4
