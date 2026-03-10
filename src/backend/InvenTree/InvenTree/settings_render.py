import os
import dj_database_url

# ─── Railway path overrides ───────────────────────────────────────────
# Railway service env vars override Dockerfile ENV values.
# If old Render paths (/opt/render/...) are still set in Railway,
# they MUST be corrected here BEFORE settings.py loads,
# because settings.py calls get_static_dir(), get_backup_dir() etc. at import time.
_RAILWAY_PATH_DEFAULTS = {
    'INVENTREE_BACKUP_DIR': '/home/inventree/backup',
    'INVENTREE_STATIC_ROOT': '/home/inventree/static',
    'INVENTREE_MEDIA_ROOT': '/home/inventree/media',
    'INVENTREE_LOG_DIR': '/home/inventree/logs',
    'INVENTREE_PLUGIN_DIR': '/usr/src/app/InvenTree/plugins',
    'INVENTREE_WEB_ROOT': '/usr/src/app/InvenTree/InvenTree/web',
}
for _key, _default in _RAILWAY_PATH_DEFAULTS.items():
    _val = os.environ.get(_key, '')
    if not _val or '/opt/render' in _val:
        os.environ[_key] = _default
# ──────────────────────────────────────────────────────────────────────

from .settings import *  # noqa

print("--- LOADING RENDER SETTINGS ---")

# Railway / production ALLOWED_HOSTS
ALLOWED_HOSTS = ['*']  # Railway handles host validation at proxy level

# Insert DB health middleware BEFORE tenancy middleware
if 'tenancy.middleware.SubdomainTenantMiddleware' in MIDDLEWARE:
    MIDDLEWARE.insert(
        MIDDLEWARE.index('tenancy.middleware.SubdomainTenantMiddleware'),
        'tenancy.db_middleware.DatabaseHealthMiddleware'
    )

# Database configuration for Render
# Render provides DATABASE_URL for managed PostgreSQL
if 'DATABASE_URL' in os.environ:
    print(f"Configuring Database from DATABASE_URL: {os.environ['DATABASE_URL'].split('@')[-1]}") # Log safe part
    
    DATABASES['default'] = dj_database_url.config(
        conn_max_age=0  # Disable pooling - fresh connection per request to avoid stale SSL connections
    )
    
    # Use standard PostgreSQL backend (django-tenants removed)
    DATABASES['default']['ENGINE'] = 'django.db.backends.postgresql'
    
    # SSL + Keepalives (keepalives help even without pooling, for long queries)
    DATABASES['default']['OPTIONS'] = {
        'sslmode': 'require',
        'connect_timeout': 30,
        'keepalives': 1,
        'keepalives_idle': 30,
        'keepalives_interval': 10,
        'keepalives_count': 5,
    }
    
    # Log configuration for debugging
    _db = DATABASES['default']
    _opts = _db.get('OPTIONS', {})
    print(f"""
=== DATABASE CONFIGURATION ===
Engine: {_db.get('ENGINE')}
Host: {_db.get('HOST', 'N/A')}
Port: {_db.get('PORT', 'N/A')}
Database: {_db.get('NAME')}
SSL Mode: {_opts.get('sslmode')}
Connection Timeout: {_opts.get('connect_timeout')}s
Connection Max Age: {_db.get('CONN_MAX_AGE', 0)}s (0 = no pooling)
TCP Keepalives: enabled={_opts.get('keepalives')}, idle={_opts.get('keepalives_idle')}s, interval={_opts.get('keepalives_interval')}s, count={_opts.get('keepalives_count')}
==============================
""")
else:
    print("WARNING: No DATABASE_URL found. Using default settings from settings.py")


# Override REST_FRAMEWORK settings for Render deployment
# Ensure API Token authentication works for Bot-Service
REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = [
    'users.authentication.ApiTokenAuthentication',  # Custom ApiToken authentication (uses ApiToken model)
    'tenancy.authentication.ServiceTokenAuthentication',
    'tenancy.authentication.TenantJWTAuthentication',
    'rest_framework.authentication.BasicAuthentication',
    'rest_framework.authentication.SessionAuthentication',
]

# Keep permissions open for now - Bot-Service doesn't have valid ServiceToken yet
# TODO: Create proper ServiceToken and switch back to IsAuthenticated
REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'] = [
    'rest_framework.permissions.AllowAny',  # Temporarily allow unauthenticated access
]

print(f"REST_FRAMEWORK AUTH CLASSES: {REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']}")
print(f"REST_FRAMEWORK PERMISSIONS: {REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']}")



def _env_bool(name: str, default: bool = False) -> bool:
    """Parse boolean-ish env vars safely."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


# Admin toggle: default False for Render, can be enabled via ENV
INVENTREE_ADMIN_ENABLED = _env_bool('INVENTREE_ADMIN_ENABLED', default=False)

# Admin URL: allow override via ENV, sanitize trailing slashes
_admin_env = os.environ.get('INVENTREE_ADMIN_URL')
if _admin_env:
    INVENTREE_ADMIN_URL = _admin_env.strip('/') or 'admin'
else:
    INVENTREE_ADMIN_URL = (locals().get('INVENTREE_ADMIN_URL') or 'admin').strip('/')  # type: ignore

# CORS override for Render (frontend on autoteile-dashboard.onrender.com)
_cors_origins = [
    'https://autoteile-dashboard.onrender.com',
    'https://wawi-new.onrender.com',
    'https://app.partsunion.de',
    'https://admin.partsunion.de',
    'https://partsunion.de',
    'https://www.partsunion.de',
    'http://localhost:5173',
    'http://localhost:4173',
    'http://127.0.0.1:5173',
]

try:
    CORS_ALLOWED_ORIGINS = list(set(CORS_ALLOWED_ORIGINS + _cors_origins))  # type: ignore
except Exception:
    CORS_ALLOWED_ORIGINS = _cors_origins

# CSRF configuration for Railway deployment
CSRF_TRUSTED_ORIGINS = [
    'https://wawi-production.up.railway.app',
    'http://wawi-production.up.railway.app',
    'https://*.up.railway.app',
    'https://*.partsunion.de',
    'http://localhost:5173',
    'http://localhost:4173',
    'http://127.0.0.1:5173',
]

CORS_ALLOW_HEADERS = [
    'authorization',
    'content-type',
    'accept',
    'origin',
    'cache-control',
    'pragma',
    'expires',
    'x-requested-with',
    'x-csrftoken',
    'x-device-id',
    'x-tenant-id',
]

CORS_ALLOW_METHODS = [
    'GET',
    'POST',
    'PUT',
    'PATCH',
    'DELETE',
    'OPTIONS',
]

# CORS credentials and preflight settings
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False

# Fix: collectstatic ignoriert oft Dot-Folder (z.B. ".vite") wenn ein ".*" Ignore aktiv ist.
# Wir setzen Ignore-Patterns explizit OHNE ".*", damit web/.vite/manifest.json mit eingesammelt wird.
STATICFILES_IGNORE_PATTERNS = [
    "CVS",
    "*~",
    "*.tmp",
    "*.temp",
]
