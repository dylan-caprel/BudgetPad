"""
Selection automatique du module settings selon la variable d'environnement
DJANGO_ENV (valeurs : 'dev' | 'prod'). Par defaut : 'dev'.
"""
import os

_env = os.getenv('DJANGO_ENV', 'dev').lower()

if _env == 'prod':
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
