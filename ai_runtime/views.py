import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from common.response import success_response
from common.permissions import AdminCodePermission
from common.exceptions import APIError
from . import models as m, services as s
from .contracts import SCENES, fail, digest, endpoint, compatible


class RuntimeThrottle(UserRateThrottle):
    rate = '30/min'
    scope = 'ai_runtime'


class TestThrottle(UserRateThrottle):
    rate = '5/min'
    scope = 'ai_runtime_test'


class Base(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [RuntimeThrottle]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        response['Pragma'] = 'no-cache'
        return response


def parsed(cls, request):
    data = cls(data=request.data)
    data.is_valid(raise_exception=True)
    return data.validated_data


class CapInput(serializers.Serializer):
    platform = serializers.ChoiceField(choices=['ios'])
    app_build = serializers.IntegerField(min_value=1)
    contract_version = serializers.IntegerField(min_value=1)
    schema_versions = serializers.ListField(child=serializers.IntegerField(), max_length=10)
    adapter_ids = serializers.ListField(child=serializers.CharField(max_length=60), max_length=10)


class Manifest(Base):
    def get(self, request):
        ch = s.channel()
        release = ch.current
        scenes = []
        if release and ch.enabled:
            for name in release.snapshot['scenes']:
                try:
                    s.enforce_control(ch, release.snapshot, [name])
                    scenes.append(name)
                except APIError:
                    pass
        minimum = release.snapshot['minimum_build'] if release else 1
        build = request.query_params.get('app_build')
        if build is not None and (not build.isdigit() or int(build) < minimum):
            fail('UPGRADE_REQUIRED', '请更新客户端后继续', 426)
        return success_response({'schema_version': 1, 'server_time': timezone.now().isoformat(),
                                 'control_version': ch.version, 'available_scenes': scenes,
                                 'minimum_build': release.snapshot['minimum_build'] if release else 1,
                                 'refresh_after_seconds': 300})


class Configuration(Base):
    def post(self, request, task_id):
        class Input(serializers.Serializer):
            request_id = serializers.UUIDField()
            client_capabilities = CapInput()
        data = parsed(Input, request)
        try:
            return success_response(s.configuration(request.user, task_id, data['client_capabilities'], data['request_id']))
        except APIError as error:
            m.Delivery.objects.create(account=request.user, task_id=task_id, request_id=data['request_id'],
                                      code=(error.details or {}).get('runtime_code', 'ERROR'))
            raise


class Events(Base):
    def post(self, request, task_id):
        from ai_production.models import ProductionTask
        task = get_object_or_404(ProductionTask, pk=task_id, account=request.user)
        class Event(serializers.Serializer):
            event_id = serializers.UUIDField()
            scene = serializers.ChoiceField(choices=list(SCENES))
            code = serializers.RegexField(r'^[A-Z0-9_]{1,60}$')
            duration_ms = serializers.IntegerField(min_value=0, max_value=3600000)
        class Input(serializers.Serializer):
            events = Event(many=True, max_length=20)
        for event in parsed(Input, request)['events']:
            m.ClientEvent.objects.get_or_create(event_id=event.pop('event_id'), defaults={'task': task, **event})
        return success_response({'accepted': True})


class AdminBase(Base):
    permission_classes = [AdminCodePermission]
    required_permission_code = 'menu:ai:runtime'

    def initial(self, request, *args, **kwargs):
        if request.method != 'GET':
            self.required_permission_code = 'button:ai:runtime:' + getattr(self, 'action_permission', 'edit')
        super().initial(request, *args, **kwargs)


class ProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Provider
        fields = ['id', 'name', 'host', 'enabled']
        read_only_fields = ['id']

    def validate_host(self, value):
        endpoint('https://' + value + '/')
        return value


class SlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.CredentialSlot
        fields = ['id', 'name', 'provider', 'active_version', 'enabled']
        read_only_fields = ['id', 'active_version']


class ModelSerializer(serializers.ModelSerializer):
    adapter_id = serializers.ChoiceField(choices=['ark_responses_v1', 'ark_images_v1'])
    capabilities = serializers.ListField(child=serializers.ChoiceField(choices=[
        'vision', 'tools', 'stream', 'image_generation', 'reference_image']), max_length=5)

    class Meta:
        model = m.Model
        fields = ['id', 'name', 'provider', 'model_id', 'adapter_id', 'endpoint', 'capabilities', 'enabled']
        read_only_fields = ['id']

    def validate(self, attrs):
        provider = attrs.get('provider', getattr(self.instance, 'provider', None))
        address = attrs.get('endpoint', getattr(self.instance, 'endpoint', ''))
        endpoint(address, provider.host)
        return attrs


CATALOG = {'providers': (m.Provider, ProviderSerializer), 'models': (m.Model, ModelSerializer),
           'credential-slots': (m.CredentialSlot, SlotSerializer)}


class Catalog(AdminBase):
    def initial(self, request, *args, **kwargs):
        if kwargs.get('kind') == 'credential-slots':
            self.action_permission = 'credential'
        super().initial(request, *args, **kwargs)

    def get(self, request, kind, pk=None):
        model, serializer = CATALOG[kind]
        if pk:
            return success_response(serializer(get_object_or_404(model, pk=pk)).data)
        return success_response({'items': serializer(model.objects.all().order_by('name'), many=True).data})

    @transaction.atomic
    def post(self, request, kind, pk=None):
        model, serializer = CATALOG[kind]
        s.channel(lock=True)
        form = serializer(data=request.data)
        form.is_valid(raise_exception=True)
        obj = form.save()
        s.audit(request.user, 'create_' + kind, obj.pk, fields=dict(form.data))
        return success_response(form.data)

    @transaction.atomic
    def patch(self, request, kind, pk):
        model, serializer = CATALOG[kind]
        s.channel(lock=True)
        obj = get_object_or_404(model.objects.select_for_update(), pk=pk)
        # Stable provider/host identities prevent credential slots from changing meaning.
        if ('provider' in request.data and str(request.data['provider']) != str(getattr(obj, 'provider_id', ''))) or (
                kind == 'providers' and 'host' in request.data and request.data['host'] != obj.host):
            fail('IMMUTABLE_IDENTITY', '请新建供应商/模型/槽位，不能修改其归属或域名', 422)
        if 'enabled' in request.data and request.data['enabled'] != obj.enabled and kind != 'models':
            from backoffice.rbac import has_permission_code
            if not request.user.is_superuser and not has_permission_code(request.user.pk, 'button:ai:runtime:control'):
                fail('PERMISSION_DENIED', '需要 AI 服务控制权限', 403)
            if not str(request.data.get('reason', '')).strip():
                fail('REASON_REQUIRED', '启用或停用服务必须填写原因', 422)
        form = serializer(obj, data=request.data, partial=True)
        form.is_valid(raise_exception=True)
        form.save()
        s.audit(request.user, 'update_' + kind, obj.pk, fields=dict(form.data), reason=str(request.data.get('reason', ''))[:500])
        return success_response(form.data)


class Credentials(AdminBase):
    action_permission = 'credential'

    def get(self, request, pk):
        get_object_or_404(m.CredentialSlot, pk=pk)
        return success_response({'items': list(m.CredentialVersion.objects.filter(slot_id=pk).order_by('-version')
                                               .values('version', 'suffix', 'fingerprint', 'created_at'))})

    @transaction.atomic
    def post(self, request, pk):
        class Input(serializers.Serializer):
            secret = serializers.CharField(trim_whitespace=False, max_length=4096)
            reason = serializers.CharField(max_length=500)
        data = parsed(Input, request)
        s.channel(lock=True)
        slot = get_object_or_404(m.CredentialSlot.objects.select_for_update(), pk=pk)
        encrypted = s.encrypt(data['secret'])
        latest = m.CredentialVersion.objects.filter(slot=slot).order_by('-version').first()
        obj = m.CredentialVersion.objects.create(slot=slot, version=(latest.version if latest else 0)+1,
            ciphertext=encrypted, fingerprint=s.hashlib.sha256(data['secret'].encode()).hexdigest(), suffix=data['secret'][-4:])
        s.audit(request.user, 'credential_created', pk, version=obj.version, reason=data['reason'])
        return success_response({'version': obj.version, 'suffix': obj.suffix})


class Activate(AdminBase):
    action_permission = 'credential'

    @transaction.atomic
    def post(self, request, pk):
        class Input(serializers.Serializer):
            version = serializers.IntegerField(min_value=1)
            expected_version = serializers.IntegerField(min_value=0)
            request_key = serializers.UUIDField()
            reason = serializers.CharField(max_length=500)
        data = parsed(Input, request)
        ch = s.channel(lock=True)
        slot = get_object_or_404(m.CredentialSlot.objects.select_for_update(), pk=pk)
        key = str(data['request_key'])
        fingerprint = digest({**data, 'request_key': key, 'slot': str(pk)})
        old = m.Audit.objects.filter(action='credential_activated', data__request_key=key).first()
        if old:
            if old.data.get('request_hash') != fingerprint:
                fail('REQUEST_CONFLICT', '激活请求内容已改变')
            return success_response({'active_version': old.data['version']})
        if slot.active_version != data['expected_version']:
            fail('REVISION_CONFLICT', '凭证版本已变化')
        get_object_or_404(m.CredentialVersion, slot=slot, version=data['version'])
        # Test current draft AND all retained task release configurations using this slot.
        snapshots = [s.snapshot(ch.draft)] + list(m.Release.objects.values_list('snapshot', flat=True))
        seen = set()
        for snap in snapshots:
            subset = {**snap, 'scenes': {n: v for n, v in snap['scenes'].items() if v['credential_slot_id'] == str(pk)}}
            if subset['scenes'] and digest(subset) not in seen:
                s.require_test(subset, s.versions_for(subset, {str(pk): data['version']}))
                seen.add(digest(subset))
        if not seen:
            fail('TEST_REQUIRED', '请先在草稿场景中绑定此凭证并测试', 422)
        slot.active_version = data['version']; slot.save()
        ch.version += 1; ch.save()
        s.audit(request.user, 'credential_activated', pk, version=data['version'], request_key=key,
                request_hash=fingerprint, reason=data['reason'])
        return success_response({'active_version': slot.active_version})


class Draft(AdminBase):
    def get(self, request):
        ch = s.channel()
        return success_response({'draft': ch.draft, 'revision': ch.revision, 'channel_version': ch.version,
                                 'current': str(ch.current_id) if ch.current_id else None,
                                 'enabled': ch.enabled, 'disabled_scenes': ch.disabled_scenes})

    @transaction.atomic
    def put(self, request):
        class Input(serializers.Serializer):
            expected_revision = serializers.IntegerField(min_value=1)
            draft = serializers.JSONField()
        data = parsed(Input, request)
        ch = s.channel(lock=True)
        if ch.revision != data['expected_revision']:
            fail('REVISION_CONFLICT', '草稿已被他人修改')
        s.snapshot(data['draft'])
        ch.draft = data['draft']; ch.revision += 1; ch.save()
        s.audit(request.user, 'draft_saved', ch.revision, draft=ch.draft)
        return self.get(request)


class Validation(AdminBase):
    def post(self, request):
        snap = s.snapshot(s.channel().draft)
        return success_response({'valid': True, 'config_hash': digest(snap), 'snapshot': snap})


class Tests(AdminBase):
    action_permission = 'test'
    def get_throttles(self):
        return [TestThrottle()] if self.request.method == 'POST' else [RuntimeThrottle()]

    def get(self, request, pk=None):
        m.TestRun.objects.filter(state__in=['queued', 'running'], created_at__lt=timezone.now()-timedelta(minutes=10)).update(
            state='failed', results={'code': 'WORKER_TIMEOUT'})
        qs = m.TestRun.objects.order_by('-created_at')
        if pk:
            row = get_object_or_404(qs, pk=pk)
            return success_response({'id': str(row.pk), 'state': row.state, 'results': row.results})
        return success_response({'items': list(qs[:100].values('id', 'state', 'results', 'config_hash', 'created_at', 'versions'))})

    @transaction.atomic
    def post(self, request):
        class Input(serializers.Serializer):
            release_id = serializers.UUIDField(required=False)
            slot_id = serializers.UUIDField(required=False)
            credential_version = serializers.IntegerField(min_value=1, required=False)
        data = parsed(Input, request)
        ch = s.channel(lock=True)
        snap = get_object_or_404(m.Release, pk=data['release_id']).snapshot if 'release_id' in data else s.snapshot(ch.draft)
        overrides = {}
        if 'slot_id' in data:
            sid = str(data['slot_id'])
            snap = {**snap, 'scenes': {n: v for n, v in snap['scenes'].items() if v['credential_slot_id'] == sid}}
            if not snap['scenes'] or 'credential_version' not in data:
                fail('INVALID_CONFIG', '请填写绑定槽位及测试凭证版本', 422)
            overrides[sid] = data['credential_version']
        run = m.TestRun.objects.create(actor=request.user, snapshot=snap, config_hash=digest(snap), versions=s.versions_for(snap, overrides))
        s.audit(request.user, 'test_requested', run.pk, config_hash=run.config_hash)
        from .tasks import run_test
        def enqueue():
            try:
                run_test.delay(str(run.pk))
            except Exception:
                m.TestRun.objects.filter(pk=run.pk).update(state='failed', results={'code': 'WORKER_UNAVAILABLE'})
        transaction.on_commit(enqueue)
        return success_response({'id': str(run.pk), 'state': run.state})


class Releases(AdminBase):
    action_permission = 'publish'

    def get(self, request, pk=None):
        fields = ('id', 'sequence', 'snapshot', 'config_hash', 'reason', 'actor_id', 'created_at')
        if pk:
            return success_response(get_object_or_404(m.Release.objects.values(*fields), pk=pk))
        return success_response({'items': list(m.Release.objects.order_by('-sequence')[:100].values(*fields))})

    def post(self, request, pk=None):
        class Input(serializers.Serializer):
            request_key = serializers.UUIDField()
            expected_channel_version = serializers.IntegerField(min_value=1)
            expected_draft_revision = serializers.IntegerField(min_value=1)
            reason = serializers.CharField(max_length=500)
        data = parsed(Input, request)
        data['request_key'] = str(data['request_key'])
        if pk:
            data['rollback_id'] = str(pk)
        result = s.publish(request.user, data, get_object_or_404(m.Release, pk=pk) if pk else None)
        return success_response({'id': str(result.pk), 'sequence': result.sequence})


class Controls(AdminBase):
    action_permission = 'control'

    def get(self, request):
        return Draft().get(request)

    @transaction.atomic
    def patch(self, request):
        class Input(serializers.Serializer):
            expected_version = serializers.IntegerField(min_value=1)
            enabled = serializers.BooleanField()
            disabled_scenes = serializers.ListField(child=serializers.ChoiceField(choices=list(SCENES)), max_length=4)
            reason = serializers.CharField(max_length=500)
        data = parsed(Input, request)
        ch = s.channel(lock=True)
        if ch.version != data['expected_version']:
            fail('REVISION_CONFLICT', '服务状态已更新，请重新加载')
        ch.enabled = data['enabled']; ch.disabled_scenes = data['disabled_scenes']; ch.version += 1; ch.save()
        s.audit(request.user, 'control_changed', ch.version, **data)
        return self.get(request)


class Records(AdminBase):
    required_permission_code = 'button:ai:runtime:audit'

    def get(self, request, kind):
        model = {'audits': m.Audit, 'deliveries': m.Delivery, 'events': m.ClientEvent}[kind]
        qs = model.objects.order_by('-created_at')
        if request.query_params.get('task_id') and kind != 'audits':
            try:
                qs = qs.filter(task_id=uuid.UUID(request.query_params['task_id']))
            except ValueError:
                fail('INVALID_FILTER', '任务 ID 格式错误', 422)
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            size = min(100, max(1, int(request.query_params.get('page_size', 25))))
        except ValueError:
            fail('INVALID_FILTER', '分页参数错误', 422)
        return success_response({'items': list(qs[(page-1)*size:page*size].values()),
                                 'pagination': {'total': qs.count(), 'page': page, 'page_size': size}})
