from datetime import timedelta
import hashlib
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Channel, Model, CredentialSlot, CredentialVersion, Binding, Release, Audit, Delivery, TestRun
from .contracts import SCENES, fail, digest, endpoint, parameters, compatible


def crypto():
    try:
        return MultiFernet([Fernet(key) for key in settings.AI_RUNTIME_ENCRYPTION_KEYS])
    except (ValueError, TypeError):
        fail('CONFIG_SERVICE_UNAVAILABLE', 'AI 配置加密服务尚未就绪', 503)


def encrypt(secret):
    if not isinstance(secret, str) or not 8 <= len(secret) <= 4096 or any(x.isspace() for x in secret) or secret.lower().startswith('bearer'):
        fail('INVALID_CREDENTIAL', '请输入不含 Bearer 前缀及空白字符的完整密钥', 422)
    return crypto().encrypt(secret.encode()).decode()


def decrypt(version):
    try:
        return crypto().decrypt(version.ciphertext.encode()).decode()
    except InvalidToken:
        fail('CONFIG_SERVICE_UNAVAILABLE', 'AI 凭证无法解密，请联系管理员', 503)


def channel(lock=False):
    qs = Channel.objects.select_for_update() if lock else Channel.objects
    obj = qs.filter(pk=1).first()
    if obj is None:
        fail('CONFIG_UNAVAILABLE', 'AI 服务配置尚未初始化', 503)
    return obj


def audit(user, action, target='', **data):
    Audit.objects.create(actor=user, action=action, target=str(target), data=data)


def snapshot(draft):
    if not isinstance(draft, dict) or set(draft) - {'minimum_build', 'scenes'}:
        fail('INVALID_CONFIG', '配置字段不正确', 422)
    minimum = draft.get('minimum_build', 1)
    if type(minimum) is not int or minimum < 1:
        fail('INVALID_CONFIG', '最低构建号必须为正整数', 422)
    scenes = draft.get('scenes', {})
    if not isinstance(scenes, dict) or 'diary.layout' not in scenes or set(scenes) - SCENES.keys():
        fail('INVALID_SCENES', '至少配置排版场景，且不得包含未知场景', 422)
    result = {'schema_version': 1, 'minimum_build': minimum, 'scenes': {}}
    for name, item in scenes.items():
        if not isinstance(item, dict) or set(item) - {'model', 'credential_slot', 'parameters', 'timeout_seconds'}:
            fail('INVALID_CONFIG', '场景配置包含未知字段', 422)
        try:
            model = Model.objects.select_related('provider').get(pk=item.get('model'), enabled=True, provider__enabled=True)
            slot = CredentialSlot.objects.get(pk=item.get('credential_slot'), provider=model.provider, enabled=True)
        except (Model.DoesNotExist, CredentialSlot.DoesNotExist, ValueError, ValidationError):
            fail('INVALID_CONFIG', '模型或同供应商凭证槽位不可用', 422)
        adapter, required = SCENES[name]
        if model.adapter_id != adapter or not required.issubset(set(model.capabilities)):
            fail('INVALID_CAPABILITIES', '模型能力不满足场景要求：' + name, 422)
        timeout = item.get('timeout_seconds', 180)
        if type(timeout) is not int or not 10 <= timeout <= 360:
            fail('INVALID_PARAMETERS', '超时必须为 10–360 秒', 422)
        result['scenes'][name] = {
            'provider_id': str(model.provider_id), 'adapter_id': model.adapter_id,
            'endpoint': endpoint(model.endpoint, model.provider.host), 'model_id': model.model_id,
            'credential_slot_id': str(slot.pk), 'parameters': parameters(adapter, item.get('parameters', {})),
            'limits': {'request_timeout_seconds': timeout},
        }
    return result


def versions_for(snap, overrides=None):
    result = {}
    for scene in snap['scenes'].values():
        sid = scene['credential_slot_id']
        slot = CredentialSlot.objects.filter(pk=sid, enabled=True, provider__enabled=True).first()
        if not slot or str(slot.provider_id) != scene['provider_id']:
            fail('CREDENTIAL_DISABLED', '场景凭证已停用', 403)
        version = (overrides or {}).get(sid, slot.active_version)
        if not CredentialVersion.objects.filter(slot=slot, version=version).exists():
            fail('CONFIG_UNAVAILABLE', '凭证尚未激活或版本不存在')
        result[sid] = version
    return result


def enforce_control(ch, snap, names):
    if not ch.enabled or set(names) & set(ch.disabled_scenes):
        fail('AI_DISABLED', 'AI 服务暂不可用，请稍后继续', 403)
    subset = {'scenes': {name: snap['scenes'][name] for name in names}}
    versions_for(subset)
    for scene in subset['scenes'].values():
        endpoint(scene['endpoint'])


def resolve(cap, required):
    ch = channel(lock=True)
    if not ch.current_id:
        fail('CONFIG_UNAVAILABLE', 'AI 服务尚未发布配置')
    compatible(cap, ch.current.snapshot, required)
    enforce_control(ch, ch.current.snapshot, required)
    return ch.current


def require_test(snap, versions):
    if not TestRun.objects.filter(config_hash=digest(snap), versions=versions, state='passed',
                                  created_at__gte=timezone.now()-timedelta(hours=24)).exists():
        fail('TEST_REQUIRED', '请先使用当前凭证通过全部场景测试（24 小时内）', 422)


@transaction.atomic
def publish(user, data, rollback=None):
    ch = channel(lock=True)
    request_hash = digest(data)
    old = Release.objects.filter(request_key=data['request_key']).first()
    if old:
        if old.request_hash != request_hash:
            fail('REQUEST_CONFLICT', '发布请求内容已改变')
        return old
    if ch.version != data['expected_channel_version'] or ch.revision != data['expected_draft_revision']:
        fail('REVISION_CONFLICT', '配置已被他人更新，请重新加载')
    snap = rollback.snapshot if rollback else snapshot(ch.draft)
    enforce_control(ch, snap, list(snap['scenes']))
    require_test(snap, versions_for(snap))
    release = Release.objects.create(sequence=ch.version, request_key=data['request_key'], request_hash=request_hash,
                                    snapshot=snap, config_hash=digest(snap), reason=data['reason'], actor=user)
    ch.current = release
    ch.version += 1
    ch.save()
    audit(user, 'rollback' if rollback else 'publish', release.pk, reason=data['reason'],
          config_hash=release.config_hash, source=str(rollback.pk) if rollback else None)
    return release


@transaction.atomic
def configuration(user, task_id, cap, request_id):
    from ai_production.services import lock_account
    from ai_production.models import ProductionTask
    lock_account(user)
    task = ProductionTask.objects.filter(pk=task_id, account=user).first()
    if not task:
        fail('TASK_NOT_FOUND', '制作任务不存在', 404)
    if not user.is_active:
        fail('AI_DISABLED', '账号不可用', 403)
    if task.expires_at <= timezone.now():
        fail('TASK_EXPIRED', '制作预占已到期，请先恢复任务', 410)
    if task.state != 'reserved':
        fail('TASK_STATE_CONFLICT', '请先恢复制作任务')
    binding = Binding.objects.select_related('release').filter(task=task).first()
    if not binding:
        fail('LEGACY_TASK', '旧任务未绑定配置，请保留作品并结束旧任务后重新制作')
    snap = binding.release.snapshot
    compatible(cap, snap, binding.required_scenes)
    ch = channel(lock=True)
    enforce_control(ch, snap, binding.required_scenes)
    scenes = {name: snap['scenes'][name] for name in binding.required_scenes}
    versions = versions_for({'scenes': scenes})
    secrets = {sid: {'version': v, 'auth_scheme': 'bearer',
                     'secret': decrypt(CredentialVersion.objects.get(slot_id=sid, version=v))}
               for sid, v in versions.items()}
    now = timezone.now()
    Delivery.objects.create(account=user, task_id=task.pk, release_id=binding.release_id,
                            request_id=request_id, code='OK', credential_versions=versions)
    return {'schema_version': 1, 'task_id': str(task.pk), 'release_id': str(binding.release_id),
            'config_hash': binding.release.config_hash, 'control_version': ch.version,
            'server_time': now.isoformat(), 'lease_expires_at': min(task.expires_at, now+timedelta(minutes=15)).isoformat(),
            'scenes': scenes, 'credentials': secrets}
