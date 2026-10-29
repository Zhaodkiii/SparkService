"""Recover only the two empty tables left by MySQL error 1071 in original 0001."""
import json
from pathlib import Path
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

class Command(BaseCommand):
    help = 'Inspect failed font initial migration; --apply backs up DDL and removes only its two empty tables.'
    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--backup-dir', default='run/font-migration-backups')
    def handle(self, *args, **options):
        if connection.vendor != 'mysql': raise CommandError('This recovery is only for MySQL.')
        if MigrationRecorder.Migration.objects.filter(app='font_library').exists():
            raise CommandError('Font migrations are recorded. Refusing partial-initial recovery.')
        expected={'font_library_fontaudit','font_library_fontfamily'}
        tables={t for t in connection.introspection.table_names() if t.startswith('font_library_')}
        if tables!=expected: raise CommandError('Expected exactly two failed-initial tables; refusing to alter this schema.')
        backup={}
        with connection.cursor() as cursor:
            for table in sorted(tables):
                quoted=connection.ops.quote_name(table)
                cursor.execute('SELECT COUNT(*) FROM '+quoted)
                if cursor.fetchone()[0]: raise CommandError('Nonempty table found. No changes made.')
                cursor.execute('SHOW CREATE TABLE '+quoted)
                backup[table]=cursor.fetchone()[1]
            cursor.execute('SELECT TABLE_NAME, REFERENCED_TABLE_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE REFERENCED_TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IN (%s,%s)',list(sorted(tables)))
            if any(row[0] not in expected for row in cursor.fetchall()):
                raise CommandError('External foreign-key references found. No changes made.')
            self.stdout.write('Confirmed: only the two expected empty tables exist; no font migration recorded.')
            if not options['apply']:
                self.stdout.write('Inspection only. Use --apply to back up DDL and remove empty migration remnants.'); return
            directory=Path(options['backup_dir']);directory.mkdir(parents=True,exist_ok=True)
            path=directory/('font-initial-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
            path.write_text(json.dumps(backup,ensure_ascii=False,indent=2))
            # No FK checks disabled, and no business data deleted. Stop app writes during recovery.
            for table in ['font_library_fontaudit','font_library_fontfamily']:
                cursor.execute('SELECT COUNT(*) FROM '+connection.ops.quote_name(table))
                if cursor.fetchone()[0]: raise CommandError('Table changed during recovery; stopped.')
                cursor.execute('DROP TABLE '+connection.ops.quote_name(table))
            self.stdout.write(self.style.SUCCESS('Empty remnants removed; DDL backup: '+str(path)))
