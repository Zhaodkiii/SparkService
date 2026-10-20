"""One resource worker for public preset ZIPs and private customization delivery ZIPs.

No Django setup or database connection is required in the worker environment.
"""
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

import oss2
import requests
from .package import process_archive

ENDPOINT = '/api/internal/diary-presets/processor/'


class ResourceWorker:
    def __init__(self, control_url, token, bucket, public_prefix='traveldiary/presets/',
                 private_prefix='traveldiary/customizations/', health_file=None, transport=requests):
        self.control_url = control_url.rstrip('/')
        self.headers = {'X-Preset-Processor': token}
        self.bucket = bucket
        self.public_prefix = public_prefix.strip('/') + '/'
        self.private_prefix = private_prefix.strip('/') + '/'
        if self.public_prefix.startswith(self.private_prefix) or self.private_prefix.startswith(self.public_prefix):
            raise ValueError('Public and private resource prefixes must not overlap')
        self.health_file = Path(health_file) if health_file else None
        self.transport = transport
        self.current_job = None
        self.current_scope = None
        self.pending = None
        self.connected = False
        self.error = ''
        self.health_lock = threading.Lock()

    def health(self):
        if not self.health_file:
            return
        with self.health_lock:
            self.health_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.health_file.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(
                pid=os.getpid(), updated_at=time.time(), protocol_version=3,
                connected=self.connected, error=self.error,
                current_job=self.current_job, current_scope=self.current_scope,
            )))
            temporary.replace(self.health_file)

    def post(self, payload):
        response = self.transport.post(self.control_url + ENDPOINT, json=payload,
                                       headers=self.headers, timeout=60)
        response.raise_for_status()
        self.connected, self.error = True, ''
        return response

    def connection_error(self, exc):
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        self.error = type(exc).__name__ + (f' HTTP {status}' if status else '')
        self.connected = False
        logging.warning('Resource worker connection failed: %s', self.error)
        self.health()

    def process(self, queue, job):
        private = queue == 'customization'
        if private:
            request_id = str(uuid.UUID(job['request_id']))
            scope = job['scope']
            if (job.get('kind') != 'delivery' or
                    not re.fullmatch(re.escape(self.private_prefix) + r'[A-Za-z0-9_-]+/' + re.escape(request_id) + '/', scope) or
                    not job['object_key'].startswith(scope + 'delivery-staging/')):
                raise ValueError('Invalid private delivery scope')
            destination = scope + 'blobs/'
        else:
            if not job['object_key'].startswith(self.public_prefix + 'staging/'):
                raise ValueError('Invalid public staging key')
            request_id = None
            destination = self.public_prefix + 'blobs/sha256/'
        if any(p in job['object_key'].split('/') for p in ('.', '..')):
            raise ValueError('Unsafe source key')

        def put(data, mime):
            key = destination + hashlib.sha256(data).hexdigest()
            self.bucket.put_object(key, data, headers={
                'Content-Type': mime, 'x-oss-object-acl': 'private',
                'Cache-Control': 'private, max-age=600' if private else 'private, max-age=31536000, immutable',
            })
            return key

        with tempfile.TemporaryDirectory(prefix='diary-resource-') as tmp:
            archive = Path(tmp) / 'source.zip'
            count = 0
            digest = hashlib.sha256()
            source = self.bucket.get_object(job['object_key'])
            try:
                with archive.open('wb') as out:
                    for chunk in source:
                        count += len(chunk)
                        if count > job['size'] or count > 1024 ** 3:
                            raise ValueError('Upload size changed')
                        digest.update(chunk)
                        out.write(chunk)
            finally:
                close = getattr(source, 'close', None)
                if close:
                    close()
            if count != job['size'] or (private and digest.hexdigest() != job['sha256']):
                raise ValueError('Upload source mismatch')
            result = process_archive(archive, Path(tmp) / 'expanded', job.get('source_id', job['id']), put, private_request_id=request_id)
            if not private and job['mode'] == 'page' and len(result['pages']) != 1:
                raise ValueError('Single-page upload must contain exactly one page')
            return result

    def report(self):
        job, payload = self.pending
        try:
            response = self.post(payload)
            logging.info('Resource job id=%s type=%s status=%s', job['id'], job['resource_type'], response.json().get('status'))
            self.pending = None
            return True
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (404, 409):
                self.pending = None
                self.connected, self.error = True, ''
                logging.info('Resource job id=%s no longer accepts this lease', job['id'])
                return True
            raise

    def run_once(self):
        """One durable queue, one claim endpoint, one pending report."""
        try:
            if self.pending:
                self.report()
                self.health()
                return True
            response = self.post({'action': 'claim'})
            self.health()
            if response.status_code == 204:
                return False
            job = response.json()
            kind = job['resource_type']
            if kind not in ('public', 'customization'):
                raise ValueError('Unsupported resource type')
            self.current_job, self.current_scope = job['id'], kind
            self.health()
            logging.info('Processing resource id=%s type=%s', job['id'], kind)
            try:
                payload = dict(id=job['id'], lease=job['lease'], result=self.process(kind, job))
            except Exception as exc:
                logging.warning('Resource processing failed id=%s type=%s error=%s', job['id'], kind, type(exc).__name__)
                payload = dict(id=job['id'], lease=job['lease'], error=type(exc).__name__ + ': package validation or storage failed')
            self.pending = (job, payload)
            self.report()
            self.current_job = self.current_scope = None
            self.health()
            return True
        except Exception as exc:
            self.current_job = self.current_scope = None
            self.connection_error(exc)
            return False

    def run(self):
        done = threading.Event()
        def heartbeat():
            while not done.wait(20):
                self.health()
        thread = threading.Thread(target=heartbeat, name='resource-heartbeat', daemon=True)
        thread.start()
        try:
            while True:
                if not self.run_once():
                    time.sleep(5)
        finally:
            done.set()


def main():
    logging.basicConfig(level=logging.INFO)
    bucket = oss2.Bucket(
        oss2.Auth(os.environ['ALIYUN_ACCESS_KEY_ID'], os.environ['ALIYUN_ACCESS_KEY_SECRET']),
        os.environ.get('PRESET_WORKER_OSS_ENDPOINT', 'https://oss-cn-beijing-internal.aliyuncs.com'),
        os.environ['ALIYUN_OSS_BUCKET'],
    )
    ResourceWorker(
        os.environ['PRESET_CONTROL_URL'], os.environ['DIARY_PRESETS_PROCESSOR_TOKEN'], bucket,
        public_prefix=os.environ.get('DIARY_PRESETS_OSS_PREFIX', 'traveldiary/presets/'),
        private_prefix=os.environ.get('CUSTOMIZATIONS_OSS_PREFIX', 'traveldiary/customizations/'),
        health_file=os.environ.get('PRESET_WORKER_HEALTH_FILE'),
    ).run()
