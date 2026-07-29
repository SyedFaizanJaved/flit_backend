"""Test settings: build the schema from current models, skipping migrations.

The migration chain is not replayable on a fresh DB (e.g. candidates.0002 re-adds
the `query` column that 0001 already creates), so tests use syncdb-style creation.
Run: python manage.py test --settings=flit_backend.test_settings
"""
from .settings import *  # noqa: F401,F403


class DisableMigrations(dict):
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()
