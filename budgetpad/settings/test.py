"""
Settings pour les tests automatises (pytest-django).
- SQLite en memoire (rapide, isolation totale)
- Hashers de mot de passe rapides
- Pas d'axes (perturbe les tests d'auth)
"""

from .base import *  # noqa: F401,F403

DEBUG = False

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Hasher rapide pour les tests (evite bcrypt qui ralentit fortement)
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Desactiver axes pour les tests
INSTALLED_APPS = [a for a in INSTALLED_APPS if a != 'axes']  # noqa: F405
MIDDLEWARE = [m for m in MIDDLEWARE if 'axes' not in m]  # noqa: F405
AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend']

# Logging minimal pendant les tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'root': {'handlers': ['null']},
}
