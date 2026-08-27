import importlib


class _PrintJob:
    def __init__(self):
        self.serial = None


class _QuerySet:
    def __init__(self, jobs):
        self._jobs = jobs

    def iterator(self, *, chunk_size):
        assert chunk_size == 1000
        return iter(self._jobs)


class _Manager:
    def __init__(self, jobs):
        self._jobs = jobs
        self.updated = []

    def filter(self, **filters):
        assert filters == {"serial__isnull": True}
        return _QuerySet(self._jobs)

    def bulk_update(self, jobs, fields):
        assert fields == ["serial"]
        self.updated.extend(jobs)


def test_print_job_serial_data_migration_generates_one_uuid_per_existing_row():
    migration = importlib.import_module(
        "apps.printers.migrations.0003_print_dispatch_and_cancellation"
    )
    jobs = [_PrintJob(), _PrintJob(), _PrintJob()]
    manager = _Manager(jobs)
    historical_model = type("HistoricalPrintJob", (), {"objects": manager})
    apps = type(
        "HistoricalApps",
        (),
        {"get_model": staticmethod(lambda app, model: historical_model)},
    )

    migration.populate_print_job_serials(apps, schema_editor=None)

    assert manager.updated == jobs
    assert all(job.serial is not None for job in jobs)
    assert len({job.serial for job in jobs}) == len(jobs)
