import pytest


@pytest.fixture(autouse=True)
def _test_settings(settings):
    # Plain static storage so templates render without a built manifest.
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.ALLOWED_HOSTS = ["testserver"]
    settings.LEARND_SHARED_SECRET = "topsecret"
    settings.SHARED_SECRET_HEADER = "X-Shared-Secret"
    settings.ALLOWED_EMAIL_DOMAINS = ["edu.esiee-it.fr"]
    settings.DISCORD_GUILD_ID = "1"
    settings.DISCORD_BASE_ROLE_ID = "10"
    settings.DISCORD_GUEST_ROLE_ID = "20"
