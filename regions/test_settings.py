from SparkService.settings import *
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']
LOGGING={'version':1,'disable_existing_loggers':True}
MIDDLEWARE=[m for m in MIDDLEWARE if 'request_logging' not in m]
REGIONS_SYNC_ENABLED=False
SECURE_SSL_REDIRECT=False

SILENCED_SYSTEM_CHECKS=['fields.W163','models.W046']
