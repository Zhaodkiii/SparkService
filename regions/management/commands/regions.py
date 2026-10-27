import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from regions.dataset import normalize
from regions.models import RegionDataset
from regions.services import stage, publish
from regions.sync import synchronize

class Command(BaseCommand):
    help='Synchronize, review, publish or export immutable administrative region datasets'
    def add_arguments(self,p):
        p.add_argument('action',choices=['sync','import-amap','import-artifact','publish','export','list','bootstrap'])
        p.add_argument('--file');p.add_argument('--dataset-version');p.add_argument('--reason');p.add_argument('--force',action='store_true')
    def handle(self,*args,**o):
        try:
            if o['action']=='bootstrap':
                from regions.dataset import validate,sha,canonical
                from regions.models import RegionState
                root=Path(__file__).resolve().parents[2]/'data'
                info=json.loads((root/'manifest.json').read_text())
                raw=(root/'mainland-regions.json').read_text();data=json.loads(raw)
                if sha(raw)!=info['sha256'] or data['dataset_version']!=info['dataset_version']:
                    raise ValueError('bootstrap_checksum_mismatch')
                validate(data['regions'])
                existing=RegionDataset.objects.filter(pk=data['dataset_version']).first()
                if existing and existing.artifact!=raw: raise ValueError('immutable_version_conflict')
                from datetime import datetime
                d,_=RegionDataset.objects.get_or_create(version=data['dataset_version'],defaults=dict(artifact=raw,
                    artifact_sha256=sha(raw),content_sha256=sha(canonical(data['regions'])),
                    fetched_at=datetime.fromisoformat(info['fetched_at']),counts=validate(data['regions'])))
                if not RegionState.objects.filter(pk=1,current__isnull=False).exists():
                    publish(d.version,'bootstrap-command','Verified bundled initial mainland dataset')
                    from datetime import timedelta
                    from django.conf import settings
                    state=RegionState.objects.get(pk=1)
                    state.last_checked_at=d.fetched_at
                    state.next_check_at=d.fetched_at+timedelta(days=settings.REGIONS_SYNC_DAYS)
                    state.save(update_fields=['last_checked_at','next_check_at'])
                self.stdout.write('Bootstrap ready: '+d.version)
            elif o['action']=='sync':
                r=synchronize(o['force']); self.stdout.write('not_due_or_locked' if r is None else f'{r.status}: {r.dataset_version} {r.error_code}')
                if r and r.status=='failed': raise CommandError(r.error_code)
            elif o['action']=='import-amap':
                d,_=stage(normalize(json.loads(Path(o['file']).read_text())));self.stdout.write(d.version)
            elif o['action']=='import-artifact':
                from regions.dataset import validate,canonical,sha
                raw=Path(o['file']).read_text();data=json.loads(raw)
                counts=validate(data['regions'])
                if data['schema_version']!=1: raise ValueError('unsupported_schema')
                existing=RegionDataset.objects.filter(pk=data['dataset_version']).first()
                if existing and existing.artifact!=raw: raise ValueError('immutable_version_conflict')
                RegionDataset.objects.get_or_create(version=data['dataset_version'],defaults=dict(artifact=raw,
                    artifact_sha256=sha(raw),content_sha256=sha(canonical(data['regions'])),fetched_at=timezone.now(),counts=counts))
                self.stdout.write(data['dataset_version'])
            elif o['action']=='publish':
                state=publish(o['dataset_version'],'management-command',o['reason']);self.stdout.write(f'Published {state.current_id}, release {state.release_sequence}')
            elif o['action']=='export':
                d=RegionDataset.objects.get(pk=o['dataset_version']);Path(o['file']).write_text(d.artifact);self.stdout.write(d.artifact_sha256)
            else:
                for d in RegionDataset.objects.order_by('-fetched_at')[:30]:self.stdout.write(f'{d.version} {d.status} {d.counts} {d.diff}')
        except (ValueError,TypeError,OSError,KeyError,RegionDataset.DoesNotExist) as e: raise CommandError(str(e))
