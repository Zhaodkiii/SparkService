"""Photo URLs are signed locally; photo bytes never pass through the API or a worker."""
from datetime import timedelta
from django.conf import settings
from diary_presets import storage as presets

def prefix():
    return getattr(settings, 'CUSTOMIZATIONS_OSS_PREFIX', 'traveldiary/customizations/').strip('/') + '/'

def scope(request):
    return f'{prefix()}{request.owner_id}/{request.id}/'

def sign(key):
    if not key.startswith(prefix()) or any(p in key.split('/') for p in ('..','.')):
        raise ValueError('Invalid private key')
    return presets.bucket().sign_url('GET', key, 600, slash_safe=True)

def upload(job):
    # Single bounded photo PUT; archives use multipart STS to support large packages.
    if job.kind == 'asset':
        if job.status != 'uploading':
            return {'id':str(job.id),'status':job.status}
        headers={'Content-Type':job.asset.mime,'x-oss-forbid-overwrite':'true'}
        return {'id':str(job.id), 'status':job.status,
                'put_headers':headers,
                'put_url':presets.bucket().sign_url('PUT', job.object_key, 900,
                    headers=headers, slash_safe=True)}
    return {'id':str(job.id), 'status':job.status, 'credentials':presets.credentials(job.object_key)}
