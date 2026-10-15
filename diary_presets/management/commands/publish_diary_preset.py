"""Trusted workstation publisher. Do not execute on the low-bandwidth API host."""
import hashlib
import json
import tempfile
import threading
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from diary_presets.models import Series, Template, Event
from diary_presets.package import process_archive
from diary_presets import storage
from diary_presets.views import publish


class Command(BaseCommand):
    help = 'Validate a local ZIP, upload directly to OSS, and publish a version in the connected database'
    def add_arguments(self, parser):
        parser.add_argument('archive', type=Path)
        parser.add_argument('--series', required=True)
        parser.add_argument('--series-title', required=True)
        parser.add_argument('--title', required=True)
        parser.add_argument('--template-id', type=uuid.UUID, required=True)
        parser.add_argument('--report', type=Path, required=True)

    def handle(self, *args, **options):
        archive = options['archive']
        hasher = hashlib.sha256()
        with archive.open('rb') as stream:
            for block in iter(lambda: stream.read(1024**2), b''): hasher.update(block)
        source_hash = hasher.hexdigest()
        existing = Template.objects.filter(id=options['template_id']).first()
        if existing and Event.objects.filter(template=existing, action='source-publish', detail__source_sha256=source_hash).exists():
            self.stdout.write('Already published identical archive; no duplicate version created')
            return
        revision = existing.revision if existing else None
        client = storage.bucket()
        futures = []
        gate = threading.Semaphore(8)
        count = 0
        with ThreadPoolExecutor(max_workers=4) as pool, tempfile.TemporaryDirectory(prefix='preset-publish-') as tmp:
            def upload(data, mime):
                nonlocal count
                key = storage.prefix() + 'blobs/sha256/' + hashlib.sha256(data).hexdigest()
                gate.acquire()
                def send():
                    try:
                        if not client.object_exists(key):
                            client.put_object(key, data, headers={'Content-Type': mime, 'Cache-Control': 'private, max-age=31536000, immutable', 'x-oss-object-acl': 'private'})
                        return key
                    finally: gate.release()
                futures.append(pool.submit(send))
                count += 1
                if count % 100 == 0: self.stdout.write(f'Prepared {count} files')
                return key
            # Stable namespace makes an identical re-run produce identical content-addressed resources.
            snapshot = process_archive(archive, Path(tmp), source_hash[:24], upload)
            for future in futures: future.result()
        with transaction.atomic():
            series, _ = Series.objects.get_or_create(slug=options['series'], defaults={'title': options['series_title']})
            template, created = Template.objects.select_for_update().get_or_create(id=options['template_id'], defaults={'series': series, 'title': options['title']})
            if not created and template.revision != revision:
                raise CommandError('Template changed while uploading; resources retained, publication not applied')
            template.series = series
            template.title = options['title']
            template.draft = snapshot
            publish(template, None)
            manifest_key = storage.prefix() + f'releases/{template.id}/{template.current.number}/package.json'
            client.put_object(manifest_key, json.dumps(template.current.snapshot['manifest'], ensure_ascii=False).encode(),
                              headers={'Content-Type': 'application/json', 'x-oss-object-acl': 'private'})
            Event.objects.create(template=template, action='source-publish', detail={'source_sha256': source_hash, 'version': template.current.number})
        report = dict(template_id=str(template.id), version=template.current.number, title=template.title,
                      series=series.slug, source_sha256=source_hash, pages=len(snapshot['pages']), files=count,
                      bytes=sum(f['byteCount'] for f in snapshot['manifest']['files']),
                      oss_prefix=storage.prefix(), page_titles=[p['data']['title'] for p in snapshot['pages']])
        options['report'].write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self.stdout.write(json.dumps(report, ensure_ascii=False))
