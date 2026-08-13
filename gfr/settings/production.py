"""
Production settings (Render + Supabase).

Set DJANGO_SETTINGS_MODULE=gfr.settings.production and configure env vars
from .env.example. Local development keeps gfr.settings.local (SQLite).

Database:
  - DATABASE_URL (Supabase PostgreSQL connection string) when set.
  - Falls back to the legacy DATABASE_* / SQLite behaviour until it is set,
    so existing deployments keep working during the migration.

Media storage:
  - Supabase Storage via its S3-compatible gateway when SUPABASE_* vars are
    set (public bucket). Otherwise keeps the filesystem default from base.
"""

import os

import dj_database_url

from .base import *  # noqa: F401,F403

DEBUG = False

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('DJANGO_ALLOWED_HOSTS', 'https://gfr-platform.onrender.com').split(',')
    if host.strip()
]
if not ALLOWED_HOSTS:
    raise ValueError(
        'DJANGO_ALLOWED_HOSTS must be set for production '
        '(comma-separated hostnames, e.g. your-app.onrender.com).'
    )

_secret = os.environ.get('DJANGO_SECRET_KEY', '')
if not _secret or _secret.startswith('django-insecure-'):
    raise ValueError('DJANGO_SECRET_KEY must be set to a strong non-insecure value in production.')
SECRET_KEY = _secret

# --- Database ------------------------------------------------------------

_database_url = os.environ.get('DATABASE_URL')
if _database_url:
    DATABASES = {
        'default': dj_database_url.parse(
            _database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
    # Supabase requires SSL on PostgreSQL connections.
    if DATABASES['default']['ENGINE'].endswith('postgresql'):
        DATABASES['default'].setdefault('OPTIONS', {})['sslmode'] = 'require'
else:
    # Legacy behaviour until DATABASE_URL is configured (SQLite by default).
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

# --- Media storage (Supabase Storage via S3-compatible API) --------------

if os.environ.get('SUPABASE_S3_ACCESS_KEY') and os.environ.get('SUPABASE_S3_SECRET_KEY'):
    STORAGES['default'] = {'BACKEND': 'gfr.storage.SupabaseStorage'}
    AWS_ACCESS_KEY_ID = os.environ['SUPABASE_S3_ACCESS_KEY']
    AWS_SECRET_ACCESS_KEY = os.environ['SUPABASE_S3_SECRET_KEY']
    AWS_STORAGE_BUCKET_NAME = os.environ.get('SUPABASE_BUCKET_NAME', '')
    AWS_S3_ENDPOINT_URL = os.environ.get('SUPABASE_S3_ENDPOINT_URL', '')
    AWS_S3_REGION_NAME = os.environ.get('SUPABASE_REGION', 'us-east-1')
    AWS_S3_ADDRESSING_STYLE = 'path'
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False

    _media_url = os.environ.get('SUPABASE_MEDIA_URL')
    if _media_url:
        MEDIA_URL = _media_url

# --- Security ------------------------------------------------------------

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
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
