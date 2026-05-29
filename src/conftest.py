"""Pytest bootstrap for tests running from /app inside Docker.

Ensures PostgreSQL test databases have the pgvector extension enabled.
"""

import pytest
from django.db import connection


@pytest.fixture(scope="session", autouse=True)
def enable_pgvector_extension(django_db_setup, django_db_blocker):
    """Enable pgvector extension in the test database before any test runs."""
    with django_db_blocker.unblock():
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")


@pytest.fixture(autouse=True)
def _disable_ssl_redirect(settings):
    """Disable SSL redirect in tests so API test client works without https."""
    settings.SECURE_SSL_REDIRECT = False
