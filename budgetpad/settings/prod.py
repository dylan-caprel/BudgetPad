"""Settings de production."""

import os
from .base import *  # noqa: F401,F403

DEBUG = False

# === HTTPS / cookies ===
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Headers de securite
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS = 'DENY'

# Si derriere un reverse-proxy HTTPS (nginx/traefik) :
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Hosts/origines de confiance (CSRF avec scheme)
_csrf_origins = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if _csrf_origins:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]

# URL admin — DOIT être défini dans .env en production (éviter le chemin devinable /admin/)
ADMIN_URL = os.getenv('ADMIN_URL') or 'admin/'
if ADMIN_URL == 'admin/':
    import logging as _log
    _log.getLogger('budgetpad.security').warning(
        "ADMIN_URL non configuré en production : URL par défaut 'admin/' utilisée. "
        "Définir ADMIN_URL dans .env pour masquer l'interface d'administration."
    )

# Logs plus verbeux en production sur le fichier app
LOGGING['loggers']['budgetpad']['level'] = 'INFO'
LOGGING['loggers']['django.request']['level'] = 'ERROR'

# === Sentry (optionnel - active si SENTRY_DSN est defini) ===
_sentry_dsn = os.getenv('SENTRY_DSN', '').strip()
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[
                DjangoIntegration(),
                LoggingIntegration(level=None, event_level=None),
            ],
            traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
            send_default_pii=False,  # ne pas envoyer PII (RGPD)
            environment=os.getenv('SENTRY_ENV', 'production'),
            release=os.getenv('APP_VERSION', 'budgetpad@unknown'),
        )
    except ImportError:
        # sentry-sdk non installe : on n'echoue pas mais on log un warning
        import logging
        logging.getLogger('budgetpad').warning(
            "SENTRY_DSN defini mais sentry-sdk non installe. "
            "Installer avec: pip install sentry-sdk"
        )
