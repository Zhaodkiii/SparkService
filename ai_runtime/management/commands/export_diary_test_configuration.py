"""Export the current runtime to a local XCTest fixture, without reserving quota."""
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from ai_runtime import services as s
from ai_runtime.models import CredentialVersion


class Command(BaseCommand):
    help = 'Export local AI integration-test configuration. Contains secrets, keep outside source control.'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)

    def handle(self, *args, **options):
        ch = s.channel()
        if not ch.current:
            raise CommandError('Publish a runtime release in the test environment first.')
        snap = ch.current.snapshot
        versions = s.versions_for(snap)
        credentials = {
            sid: {'version': version, 'auth_scheme': 'bearer',
                  'secret': s.decrypt(CredentialVersion.objects.get(slot_id=sid, version=version))}
            for sid, version in versions.items()
        }
        now = timezone.now().replace(microsecond=0)
        value = dict(schema_version=1, task_id=str(uuid.uuid4()), release_id=str(ch.current_id),
                     config_hash=ch.current.config_hash, control_version=ch.version,
                     server_time=now.isoformat(), lease_expires_at=(now + timedelta(minutes=15)).isoformat(),
                     scenes=snap['scenes'], credentials=credentials)
        path = Path(options['output']).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as target:
            json.dump(value, target)
        os.chmod(path, 0o600)
        self.stdout.write('Local test configuration written.')
