import hashlib
import json
from urllib.parse import urlsplit
from django.conf import settings
from common.exceptions import APIError

SCENES = {
    'diary.layout': ('ark_responses_v1', {'vision', 'tools', 'stream'}),
    'diary.background.design': ('ark_responses_v1', {'vision', 'tools'}),
    'diary.background.generate': ('ark_images_v1', {'image_generation', 'reference_image'}),
    'diary.background.review': ('ark_responses_v1', {'vision', 'tools'}),
}

def fail(code, message, status=409):
    raise APIError(message, code=status * 100 + 70, status_code=status,
                   details={'runtime_code': code, 'retryable': status in (429, 503)})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def endpoint(value, host=None):
    try:
        u = urlsplit(value)
        approved = settings.AI_RUNTIME_ALLOWED_HOSTS
        if (u.scheme != 'https' or not u.hostname or u.hostname not in approved or
                (host and u.hostname != host) or u.port not in (None, 443) or
                u.username or u.password or u.query or u.fragment or not u.path.startswith('/')):
            raise ValueError()
    except (ValueError, TypeError):
        fail('INVALID_ENDPOINT', '供应商地址必须为部署白名单中的 HTTPS 地址', 422)
    return value


def parameters(adapter, value):
    if not isinstance(value, dict):
        fail('INVALID_PARAMETERS', '参数必须为对象', 422)
    if adapter == 'ark_responses_v1':
        allowed = {'max_output_tokens', 'thinking', 'reasoning'}
        if 'max_output_tokens' in value and (type(value['max_output_tokens']) is not int or not 256 <= value['max_output_tokens'] <= 32768):
            fail('INVALID_PARAMETERS', '输出上限应为 256–32768', 422)
        if 'thinking' in value and value['thinking'] not in ({'type': 'enabled'}, {'type': 'disabled'}):
            fail('INVALID_PARAMETERS', '不支持的 thinking 参数', 422)
        if 'reasoning' in value and value['reasoning'] not in [{'effort': x} for x in ('low', 'medium', 'high')]:
            fail('INVALID_PARAMETERS', '不支持的 reasoning 参数', 422)
    elif adapter == 'ark_images_v1':
        allowed = {'size', 'watermark', 'response_format'}
        if 'size' in value and value['size'] not in ('1K', '2K', '4K'):
            fail('INVALID_PARAMETERS', '不支持的图片尺寸', 422)
        if 'watermark' in value and type(value['watermark']) is not bool:
            fail('INVALID_PARAMETERS', 'watermark 必须为布尔值', 422)
        if value.get('response_format', 'url') != 'url':
            fail('INVALID_PARAMETERS', '当前图片适配器只支持 URL', 422)
    else:
        fail('UPGRADE_REQUIRED', '不支持的适配器', 426)
    if set(value) - allowed:
        fail('INVALID_PARAMETERS', '存在不允许下发的参数', 422)
    return value


def compatible(cap, snapshot, required):
    if not isinstance(cap, dict) or cap.get('platform') != 'ios' or cap.get('contract_version') != 1:
        fail('UPGRADE_REQUIRED', '请更新客户端后继续', 426)
    if type(cap.get('app_build')) is not int or cap['app_build'] < snapshot.get('minimum_build', 1):
        fail('UPGRADE_REQUIRED', '请更新客户端后继续', 426)
    if 1 not in cap.get('schema_versions', []):
        fail('UPGRADE_REQUIRED', '配置协议不兼容，请更新客户端', 426)
    if not isinstance(required, list) or not required or len(required) != len(set(required)) or set(required) - SCENES.keys():
        fail('INVALID_SCENES', '制作场景无效', 422)
    for name in required:
        scene = snapshot.get('scenes', {}).get(name)
        if not scene:
            fail('CONFIG_UNAVAILABLE', '所需 AI 场景尚未配置')
        if scene['adapter_id'] not in cap.get('adapter_ids', []):
            fail('UPGRADE_REQUIRED', '当前客户端不支持该模型协议', 426)
