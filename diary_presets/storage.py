"""Control plane only: signing and HEAD. Never proxy resource bodies."""
import json
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def prefix():
    return getattr(settings, 'DIARY_PRESETS_OSS_PREFIX', 'traveldiary/presets/').strip('/') + '/'


def bucket():
    import oss2
    if not settings.ALIYUN_ACCESS_KEY_ID or not settings.ALIYUN_ACCESS_KEY_SECRET:
        raise ImproperlyConfigured('OSS credentials not configured')
    return oss2.Bucket(oss2.Auth(settings.ALIYUN_ACCESS_KEY_ID, settings.ALIYUN_ACCESS_KEY_SECRET),
                       settings.ALIYUN_OSS_ENDPOINT, settings.ALIYUN_OSS_BUCKET)


def sign(key):
    from diary_customizations.storage import prefix as private_prefix
    if not key.startswith((prefix() + 'blobs/', private_prefix())):
        raise ValueError('Invalid resource key')
    return bucket().sign_url('GET', key, 900, slash_safe=True)


def credentials(key):
    from aliyunsdkcore.client import AcsClient
    from aliyunsdksts.request.v20150401.AssumeRoleRequest import AssumeRoleRequest
    role = getattr(settings, 'DIARY_PRESETS_UPLOAD_ROLE_ARN', '')
    if not role:
        raise ImproperlyConfigured('DIARY_PRESETS_UPLOAD_ROLE_ARN is required; static credentials are never returned')
    request = AssumeRoleRequest()
    request.set_RoleArn(role)
    request.set_RoleSessionName('diary-preset-upload')
    request.set_DurationSeconds(3600)
    request.set_Policy(json.dumps({'Version': '1', 'Statement': [{
        'Effect': 'Allow', 'Action': ['oss:PutObject', 'oss:AbortMultipartUpload', 'oss:ListParts'],
        'Resource': [f'acs:oss:*:*:{settings.ALIYUN_OSS_BUCKET}/{key}']
    }]}))
    response = json.loads(AcsClient(settings.ALIYUN_ACCESS_KEY_ID,
                                   settings.ALIYUN_ACCESS_KEY_SECRET,
                                   settings.ALIYUN_OSS_REGION).do_action_with_exception(request))['Credentials']
    return dict(accessKeyId=response['AccessKeyId'], accessKeySecret=response['AccessKeySecret'],
                stsToken=response['SecurityToken'], expiration=response['Expiration'],
                bucket=settings.ALIYUN_OSS_BUCKET, region='oss-' + settings.ALIYUN_OSS_REGION,
                endpoint=settings.ALIYUN_OSS_ENDPOINT, key=key)
