"""Only synthetic probes; pinned public IP and TLS hostname verification, no redirects."""
import base64
import http.client
import io
import ipaddress
import json
import socket
import ssl
import certifi
import time
from urllib.parse import urlsplit
from celery import shared_task
from PIL import Image
from django.db import transaction
from django.conf import settings
from .models import TestRun, CredentialVersion
from .services import decrypt, audit
from .contracts import endpoint


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if addresses and any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses) and getattr(settings, 'AI_RUNTIME_TEST_DOH_FALLBACK', False):
            # Explicit local TUN/Fake-IP compatibility. Query a fixed trusted resolver without credentials;
            # connect only its vetted global address and retain upstream TLS hostname verification.
            import httpx
            answer = httpx.get('https://dns.google/resolve', params={'name': self.host, 'type': 'A'}, timeout=15).json()
            ips = [item['data'] for item in answer.get('Answer', []) if item.get('type') == 1]
            addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, self.port)) for ip in ips]
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('NON_PUBLIC_ADDRESS')
        # Connect the exact vetted IP; TLS still validates the configured host.
        self.sock = socket.create_connection((addresses[0][4][0], self.port), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def probe(scene, key, streaming=False):
    address = urlsplit(endpoint(scene['endpoint']))
    connection = PinnedHTTPSConnection(address.hostname, timeout=90, context=ssl.create_default_context(cafile=certifi.where()))
    stream = io.BytesIO()
    Image.new('RGB', (32, 32), '#d5a060').save(stream, format='PNG')
    image = 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()
    if scene['adapter_id'] == 'ark_images_v1':
        body = {'model': scene['model_id'], 'prompt': 'Draw a plain beige paper texture. No text.',
                'image': image, 'size': '2K', 'response_format': 'url', 'stream': False}
    else:
        body = {'model': scene['model_id'], 'stream': streaming, 'store': False,
                'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'Inspect this color square and call report_ok with ok=true.'},
                                                      {'type': 'input_image', 'image_url': image}]}],
                'tools': [{'type': 'function', 'name': 'report_ok', 'description': 'Report test success',
                           'parameters': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']}}],
                'tool_choice': 'required', 'max_output_tokens': 512}
    body.update(scene['parameters'])
    try:
        connection.request('POST', address.path, body=json.dumps(body).encode(),
                           headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        response = connection.getresponse()
        raw = response.read(2_000_001)
        if not 200 <= response.status < 300 or len(raw) > 2_000_000:
            return {'passed': False, 'status': response.status, 'code': 'UPSTREAM_REJECTED'}
        if streaming:
            if 'text/event-stream' not in response.getheader('Content-Type', ''):
                return {'passed': False, 'code': 'INVALID_STREAM'}
            events = [json.loads(line[5:].strip()) for line in raw.decode().splitlines()
                      if line.startswith('data:') and line[5:].strip() != '[DONE]']
            obj = next((e['response'] for e in events if e.get('type') == 'response.completed'), {})
        else:
            obj = json.loads(raw)
        if scene['adapter_id'] == 'ark_images_v1':
            valid = bool(obj.get('data') and str(obj['data'][0].get('url', '')).startswith('https://'))
        else:
            valid = any(o.get('type') == 'function_call' and o.get('name') == 'report_ok'
                        and json.loads(o.get('arguments', '{}')).get('ok') is True for o in obj.get('output', []))
        return {'passed': valid, 'status': response.status, 'code': 'OK' if valid else 'CAPABILITY_FAILED'}
    finally:
        connection.close()


@shared_task(soft_time_limit=420, time_limit=450)
def run_test(test_id):
    # Duplicate queue deliveries must not repeat paid probes.
    with transaction.atomic():
        run = TestRun.objects.select_for_update().get(pk=test_id)
        if run.state != 'queued':
            return
        run.state = 'running'; run.save(update_fields=['state'])
    results = {}
    try:
        for name, scene in run.snapshot['scenes'].items():
            start = time.monotonic()
            version = CredentialVersion.objects.get(slot_id=scene['credential_slot_id'], version=run.versions[scene['credential_slot_id']])
            try:
                result = probe(scene, decrypt(version), streaming=name == 'diary.layout')
            except Exception:
                # Exceptions may contain credentials or provider bodies; never persist/print them.
                result = {'passed': False, 'code': 'PROBE_FAILED'}
            result['duration_ms'] = round((time.monotonic()-start)*1000)
            results[name] = result
    finally:
        run.results = results
        run.state = 'passed' if len(results) == len(run.snapshot['scenes']) and all(x['passed'] for x in results.values()) else 'failed'
        run.save(update_fields=['state', 'results'])
        audit(run.actor, 'test_finished', run.pk, state=run.state, results=results)
