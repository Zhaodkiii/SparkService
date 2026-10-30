from SparkService.settings import *
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
SILENCED_SYSTEM_CHECKS = ['fields.W163', 'models.W046']
LOGGING = {'version': 1, 'disable_existing_loggers': True}
MIDDLEWARE = [m for m in MIDDLEWARE if 'request_logging' not in m]

CACHES = {**CACHES, 'material_pagination': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'material-pagination-tests'}}
