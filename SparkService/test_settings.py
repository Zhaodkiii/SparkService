"""Isolated SQLite model tests; historical MySQL migrations are checked separately.

Run: python manage.py test --settings=SparkService.test_settings
"""
from SparkService.settings import *  # noqa: F403

DEBUG = True
SECURE_SSL_REDIRECT = False
SECRET_KEY = 'traveldiary-tests-only-key-never-use-for-deployment'
SIMPLE_JWT = {**SIMPLE_JWT, 'SIGNING_KEY': SECRET_KEY}
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
MIGRATION_MODULES = {name.rsplit('.', 1)[-1]: None for name in INSTALLED_APPS}
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
ALIYUN_SMS_ACCESS_KEY_ID = ''
ALIYUN_SMS_ACCESS_KEY_SECRET = ''
APNS_AUTH_KEY_PATH = ''
LOGGING_CONFIG = None
