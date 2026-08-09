"""
Production settings (PythonAnywhere and similar hosts).

Set DJANGO_SETTINGS_MODULE=gfr.settings.production and configure env vars
from .env.example. Keeps SQLite until you switch DATABASE_* to MySQL/Postgres.
"""

import os

from .base import *  # noqa: F401,F403

DEBUG = False

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')
    if host.strip()
]
if not ALLOWED_HOSTS:
    raise ValueError(
        'DJANGO_ALLOWED_HOSTS must be set for production '
        '(comma-separated hostnames, e.g. yourusername.pythonanywhere.com).'
    )

_secret = os.environ.get('DJANGO_SECRET_KEY', '')
if not _secret or _secret.startswith('django-insecure-'):
    raise ValueError('DJANGO_SECRET_KEY must be set to a strong non-insecure value in production.')
SECRET_KEY = _secret

# Default: same SQLite file as local (demo / interim). Switch via env when ready.
_db_engine = os.environ.get('DATABASE_ENGINE', 'django.db.backends.sqlite3')
if _db_engine == 'django.db.backends.sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.environ.get('DATABASE_NAME', str(BASE_DIR / 'db.sqlite3')),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': _db_engine,
            'NAME': os.environ['DATABASE_NAME'],
            'USER': os.environ.get('DATABASE_USER', ''),
            'PASSWORD': os.environ.get('DATABASE_PASSWORD', ''),
            'HOST': os.environ.get('DATABASE_HOST', ''),
            'PORT': os.environ.get('DATABASE_PORT', ''),
            'OPTIONS': {'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"}
            if 'mysql' in _db_engine
            else {},
        }
    }

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]
