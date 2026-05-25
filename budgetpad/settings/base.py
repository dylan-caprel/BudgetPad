"""
Settings communs BudgetPAD.
Surchargees dans dev.py et prod.py.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# BASE_DIR pointe vers le repertoire qui contient manage.py
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in .env file")

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 'crispy_forms', 'crispy_bootstrap5',  # supprime Sprint 1 - non utilise
    'axes',
    'django_filters',
    'core',
]

# Pagination par defaut
PAGINATION_PAGE_SIZE = 25

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',  # doit etre AVANT le middleware d'app
    'core.middleware.ForcePasswordChangeMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# === django-axes : anti brute-force ===
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # heure(s)
# Liste imbriquee = ET : verrouille seulement la combinaison (username + ip),
# pas tous les comptes partageant une IP (utile en dev/local).
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = 'registration/lockout.html'

ROOT_URLCONF = 'budgetpad.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.notifications_count',
                'core.context_processors.exercices_context',
            ],
            'libraries': {
                'budget_filters': 'core.templatetags.budget_filters',
            },
        },
    },
]

WSGI_APPLICATION = 'budgetpad.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.mysql'),
        'NAME': os.getenv('DB_NAME', 'budgetpad'),
        'USER': os.getenv('DB_USER', 'root'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        }
    }
}

AUTH_USER_MODEL = 'core.Utilisateur'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Douala'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Fichiers uploadés par les utilisateurs (pièces jointes)
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 Mo en mémoire avant disque
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024   # limite globale POST

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Repertoire pour les logs
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} ({module}) — {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_app': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'budgetpad.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'file_security': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'security.log'),
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'budgetpad': {
            'handlers': ['console', 'file_app'],
            'level': 'INFO',
            'propagate': False,
        },
        'budgetpad.security': {
            'handlers': ['console', 'file_security'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file_app'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
