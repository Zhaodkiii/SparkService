"""Conditional GET for explicitly opted-in, read-only catalog representations.

Runs AFTER authentication, visibility checks and serialization. Never bypasses a
view or shares response bodies between users. Weak validators ignore only OSS
signature churn, and rotate every ten minutes (signed previews last >= 15 min).
"""
import hashlib
import json
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.http import HttpResponseNotModified
from django.utils.cache import patch_vary_headers
from common.http_cache import etag_matches


_PATHS = re.compile(
    r'^/api/v1/(?:'
    r'fonts/(?:families/(?:[^/]+/)?|mine/)|'
    r'materials/(?:categories/|tags/|available/|libraries/(?:[^/]+/(?:items/)?)?|items/(?:[^/]+/)?)|'
    r'diary-presets/(?:catalog/|search/|taxonomy/)|'
    r'support/(?:config/|help/categories/|help/articles/(?:[^/]+/)?)'
    r')$'
)
_SIGNATURE_KEYS = {'ossaccesskeyid', 'signature', 'expires', 'security-token',
                   'x-oss-signature', 'x-oss-date', 'x-oss-expires', 'x-oss-credential',
                   'x-oss-security-token'}


def semantic_value(value):
    if isinstance(value, dict):
        # expires_at here describes the signed image URL, not a business deadline.
        return {key: semantic_value(item) for key, item in value.items()
                if not (key == 'expires_at' and 'url' in value and 'sha256' in value)}
    if isinstance(value, list):
        return [semantic_value(item) for item in value]
    if isinstance(value, str) and value.startswith('https://'):
        parts = urlsplit(value)
        if (parts.hostname or '').endswith('.aliyuncs.com'):
            query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                     if k.lower() not in _SIGNATURE_KEYS]
            return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(sorted(query)), parts.fragment))
    return value


class CatalogConditionalGetMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (request.method != 'GET' or not _PATHS.fullmatch(request.path)
                or response.status_code != 200 or response.streaming
                or response.has_header('ETag')
                or 'no-store' in response.get('Cache-Control', '').lower()
                or 'application/json' not in response.get('Content-Type', '')):
            return response
        try:
            value = json.loads(response.content)
        except (ValueError, UnicodeDecodeError):
            return response
        representation = [request.get_full_path(), request.headers.get('Authorization', ''),
                          request.headers.get('X-Billing-Session', ''), int(time.time() // 600),
                          semantic_value(value)]
        digest = hashlib.sha256(json.dumps(representation, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        etag = f'W/"{digest}"'
        if etag_matches(request.headers.get('If-None-Match'), etag):
            result = HttpResponseNotModified()
            # Preserve tracing/security/CORS metadata established by the view.
            for key, item in response.items():
                if key.lower() not in ('content-type', 'content-length'):
                    result[key] = item
            result.cookies = response.cookies
            response = result
        response['ETag'] = etag
        response['Cache-Control'] = 'private, max-age=300'
        patch_vary_headers(response, ['Authorization', 'X-Billing-Session', 'Accept-Language'])
        return response
