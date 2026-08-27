import importlib


class _Batch:
    def __init__(self):
        self.serial = None


class _QuerySet:
    def __init__(self, batches):
        self._batches = batches

    def iterator(self, *, chunk_size):
        assert chunk_size == 1000
        return iter(self._batches)


class _Manager:
    def __init__(self, batches):
        self._batches = batches
        self.updated = []

    def filter(self, **filters):
        assert filters == {"serial__isnull": True}
        return _QuerySet(self._batches)

    def bulk_update(self, batches, fields):
        assert fields == ["serial"]
        self.updated.extend(batches)


def test_order_batch_serial_data_migration_generates_one_uuid_per_existing_row():
    migration = importlib.import_module(
        "apps.orders.migrations.0004_kitchen_dispatch_grace_period"
    )
    batches = [_Batch(), _Batch(), _Batch()]
    manager = _Manager(batches)
    historical_model = type("HistoricalOrderBatch", (), {"objects": manager})
    apps = type(
        "HistoricalApps",
        (),
        {"get_model": staticmethod(lambda app, model: historical_model)},
    )

    migration.populate_order_batch_serials(apps, schema_editor=None)

    assert manager.updated == batches
    assert all(batch.serial is not None for batch in batches)
    assert len({batch.serial for batch in batches}) == len(batches)
