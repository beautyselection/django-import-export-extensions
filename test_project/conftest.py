from django.conf import settings

import pytest


def pytest_configure() -> None:
    """Set up Django settings for tests.

    `pytest` automatically calls this function once when tests are run.

    """
    settings.TESTING = True


@pytest.fixture(scope="session", autouse=True)
def django_db_setup(django_db_setup):
    """Set up test db for testing."""


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(django_db_setup, db):
    """Allow all tests to access DB."""


@pytest.fixture(scope="session", autouse=True)
def _temp_directory_for_media(tmpdir_factory):
    """Fixture that set temp directory for all media files.

    This fixture changes DEFAULT_FILE_STORAGE or STORAGES variable
    to filesystem and provides temp dir for media.
    PyTest cleans up this temp dir by itself after few test runs

    """
    if hasattr(settings, "STORAGES"):
        settings.STORAGES["default"]["BACKEND"] = (
            "django.core.files.storage.FileSystemStorage"
        )
    else:
        settings.DEFAULT_FILE_STORAGE = (
            "django.core.files.storage.FileSystemStorage"
        )
    media = tmpdir_factory.mktemp("tmp_media")
    settings.MEDIA_ROOT = media
