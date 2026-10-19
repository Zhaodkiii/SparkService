"""Dedicated OSS-region worker, also available as an opt-in local process."""
import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
import oss2
import requests
from diary_presets.package import process_archive

logging.basicConfig(level=logging.INFO)
api = os.environ['PRESET_CONTROL_URL'].rstrip('/') + '/api/internal/diary-presets/processor/'
headers = {'X-Preset-Processor': os.environ['DIARY_PRESETS_PROCESSOR_TOKEN']}
# Dedicated worker credentials must not be shared with browser STS upload role.
auth = oss2.Auth(os.environ['ALIYUN_ACCESS_KEY_ID'], os.environ['ALIYUN_ACCESS_KEY_SECRET'])
bucket = oss2.Bucket(auth, os.environ.get('PRESET_WORKER_OSS_ENDPOINT', 'https://oss-cn-beijing-internal.aliyuncs.com'), os.environ['ALIYUN_OSS_BUCKET'])
prefix = os.environ.get('DIARY_PRESETS_OSS_PREFIX', 'traveldiary/presets/').strip('/') + '/'

def health(connected, error='', current_job=None):
    path = os.environ.get('PRESET_WORKER_HEALTH_FILE')
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(pid=os.getpid(), updated_at=time.time(),
                                         connected=connected, error=error, current_job=current_job)))
    temporary.replace(target)

def post(payload):
    result = requests.post(api, json=payload, headers=headers, timeout=60)
    result.raise_for_status()
    return result

def put(data, mime):
    key = prefix + 'blobs/sha256/' + hashlib.sha256(data).hexdigest()
    bucket.put_object(key, data, headers={'Content-Type': mime, 'Cache-Control': 'private, max-age=31536000, immutable', 'x-oss-object-acl': 'private'})
    health(True, current_job=job['id'])
    return key

while True:
    try:
        response = post({'action': 'claim'})
        health(True)
        if response.status_code == 204:
            time.sleep(10)
            continue
        job = response.json()
        health(True, current_job=job['id'])
        logging.info('Processing upload %s', job['id'])
        result = None
        try:
            if not job['object_key'].startswith(prefix + 'staging/'):
                raise ValueError('Invalid staging key')
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / 'source.zip'
                # Limit bytes even if upload source is changed after complete.
                source = bucket.get_object(job['object_key'])
                total = 0
                with archive.open('wb') as out:
                    for chunk in source:
                        total += len(chunk)
                        if total > job['size'] or total > 1024**3:
                            raise ValueError('Upload size changed')
                        out.write(chunk)
                if total != job['size']:
                    raise ValueError('Upload size changed')
                result = process_archive(archive, Path(tmp) / 'expanded', job['id'], put)
                if job['mode'] == 'page' and len(result['pages']) != 1:
                    raise ValueError('Single-page upload must contain exactly one page')
            payload = dict(id=job['id'], lease=job['lease'], result=result)
        except Exception as exc:
            payload = dict(id=job['id'], lease=job['lease'], error=str(exc)[:1000])
        response = post(payload)
        health(True)
        logging.info('Upload %s status=%s', job['id'], response.json().get('status'))
    except Exception as exc:
        # HTTP exception strings may contain addresses or credentials.
        code = getattr(getattr(exc, 'response', None), 'status_code', None)
        error = type(exc).__name__ + (f' HTTP {code}' if code else '')
        health(False, error)
        logging.error('Processor request failed: %s', error)
        time.sleep(15)
