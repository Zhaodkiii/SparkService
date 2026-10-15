"""One-time, explicitly requested reset of this application's MySQL schema."""
import os
import re
import pymysql
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SparkService.settings")
from django.conf import settings

requested = os.environ.get('RESET_DATABASE_NAME', '')
config = settings.DATABASES['default']
name = config['NAME']
if os.environ.get('RELEASE_TARGET_IP') != '39.106.39.110':
    raise RuntimeError('Database reset target is not the authorized server')
if not requested or requested != name or not re.fullmatch(r'[A-Za-z0-9_]+', name):
    raise RuntimeError('Database reset name must exactly match the configured application database')
if name in {'mysql', 'information_schema', 'performance_schema', 'sys'}:
    raise RuntimeError('System databases must not be reset')
connection = pymysql.connect(host=config['HOST'], port=int(config['PORT']), user=config['USER'], password=config['PASSWORD'], connect_timeout=10, autocommit=True)
try:
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s', (name,))
        print(f'Resetting authorized application schema {name}; old table count={cursor.fetchone()[0]}', flush=True)
        cursor.execute(f'DROP DATABASE IF EXISTS `{name}`')
        cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        print('Database recreated empty', flush=True)
finally:
    connection.close()
