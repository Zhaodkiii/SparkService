"""Live OSS/local database verification; signed URLs and credentials are never printed."""
import hashlib
import json
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests
from django.core.management.base import BaseCommand, CommandError
from diary_presets.models import Template
from diary_presets.domain import select
from diary_presets import storage


class Command(BaseCommand):
    help = 'Verify remote resource metadata and download every dependency of the first page directly from OSS'
    def add_arguments(self, parser):
        parser.add_argument('template_id')
        parser.add_argument('--report', type=Path, required=True)
    def handle(self,*args,**options):
        template=Template.objects.select_related('current').get(pk=options['template_id'])
        snap=template.current.snapshot
        b=storage.bucket()
        unique={snap['keys'][f['path']]:f for f in snap['manifest']['files']}
        def check(item):
            key,f=item
            if b.head_object(key).content_length != f['byteCount']: raise CommandError('Object length mismatch')
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(check,unique.items()))
        first=snap['pages'][0]['data']['id']
        page=select(snap,[first])
        fetched=0
        for f in page['manifest']['files']:
            response=requests.get(storage.sign(page['keys'][f['path']]),timeout=120)
            if response.status_code != 200: raise CommandError(f'OSS dependency GET failed HTTP {response.status_code}')
            if len(response.content)!=f['byteCount'] or hashlib.sha256(response.content).hexdigest()!=f['sha256']:
                raise CommandError('Downloaded dependency checksum mismatch')
            fetched+=len(response.content)
        sample=max(snap['manifest']['files'],key=lambda f:f['byteCount'])
        url=storage.sign(snap['keys'][sample['path']])
        response=requests.get(url,headers={'Range':'bytes=0-1023'},timeout=30)
        if response.status_code!=206 or len(response.content)!=1024:
            raise CommandError('OSS range retrieval failed')
        anonymous=requests.get(url.split('?')[0],timeout=30)
        if anonymous.status_code!=403: raise CommandError('Resource is not private')
        report=dict(template_id=str(template.id),version=template.current.number,pages=len(snap['pages']),
                    remote_objects_checked=len(unique),single_page_files=len(page['manifest']['files']),
                    single_page_download_bytes=fetched,book_bytes=sum(f['byteCount'] for f in snap['manifest']['files']),
                    range_status=response.status_code,anonymous_status=anonymous.status_code,
                    single_page_hashes='passed',page_order=[p['data']['title'] for p in snap['pages']])
        options['report'].write_text(json.dumps(report,ensure_ascii=False,indent=2))
        self.stdout.write(json.dumps({k:v for k,v in report.items() if k!='page_order'},ensure_ascii=False))
