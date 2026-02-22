from .settings import *

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

MIGRATION_MODULES = {
    "core": None,
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
TICKET_SYSTEM_EMAIL = "tickets@example.local"
