import hashlib
import json
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from billing.models import ContentOffer
from .models import *
from .schemas import Content

def canonical(value):
    return json.loads(json.dumps(value, default=str))

def digest(value):
    return hashlib.sha256(json.dumps(canonical(value), sort_keys=True, separators=(',',':')).encode()).hexdigest()

def normalize(data):
    form=Content(data=data);form.is_valid(raise_exception=True)
    return canonical(form.validated_data)

def issues(family, content, policy=True):
    errors=[]; ids=[]
    if not content.get('faces'): errors.append('上传并验证字体文件')
    faces=content.get('faces',[])
    if len({f['id'] for f in faces}) != len(faces): errors.append('字面标识不能重复')
    if content.get('default_face') not in [f['id'] for f in faces]: errors.append('选择默认字面')
    for f in faces:
        asset=FontAsset.objects.filter(pk=f['asset_id'], family=family, kind='font').first()
        if not asset or f['postscript_name'] not in [x['postscript_name'] for x in asset.metadata.get('faces',[])]:
            errors.append('字体字面未经可信处理器验证')
        else: ids.append(asset.pk)
    for field,kind in [('cover','cover'),('license_asset','license')]:
        asset=FontAsset.objects.filter(pk=content.get(field),family=family,kind=kind).first()
        if not asset: errors.append('缺少已验证'+('封面' if kind=='cover' else '授权附件'))
        else: ids.append(asset.pk)
    for asset_id in content.get('previews',[]):
        asset=FontAsset.objects.filter(pk=asset_id,family=family,kind='preview').first()
        if not asset: errors.append('详情图片无效')
        else: ids.append(asset.pk)
    if not content.get('previews'): errors.append('至少添加一张详情图')
    if not content.get('languages'): errors.append('填写支持语言')
    if not content.get('license_approved') or not {'app','distribution'}.issubset(content.get('license_scopes',[])):
        errors.append('确认 App 嵌入及分发授权')
    offer=ContentOffer.objects.select_related('current_policy_revision').filter(target_kind='font',target_id=family.pk).first()
    if policy and (not offer or offer.state!='active' or not offer.current_policy_revision_id): errors.append('先发布有效收费策略')
    if policy and offer and offer.current_policy_revision and offer.current_policy_revision.access_mode!='free' and 'paid_service' not in content.get('license_scopes',[]): errors.append('确认付费服务授权')
    return list(dict.fromkeys(errors)),ids

@transaction.atomic
def publish(family_id, expected_revision, expected_base, key, actor):
    family=FontFamily.objects.select_for_update().get(pk=family_id)
    request_hash=digest([expected_revision,expected_base])
    previous=FontPublishOperation.objects.filter(family=family,key=key).first()
    if previous:
        if previous.digest!=request_hash: raise ValidationError('发布幂等键参数冲突')
        return previous.release
    draft=FontDraft.objects.select_for_update().get(family=family)
    current=family.current.number if family.current_id else 0
    if draft.revision!=expected_revision or current!=expected_base: raise ValidationError('草稿或线上版本已变更，请刷新')
    # Lock the same offer used by pricing publication, so access-policy changes cannot race this commit.
    list(ContentOffer.objects.select_for_update().filter(target_kind='font',target_id=family.pk))
    errors,ids=issues(family,draft.content)
    if errors: raise ValidationError({'issues':errors})
    release=FontRelease.objects.create(family=family,number=current+1,content=draft.content,digest=digest(draft.content),actor=actor)
    release.assets.set(ids)
    family.current=release;family.active=True;family.title=draft.content['title'];family.state_revision+=1
    family.first_published_at=family.first_published_at or timezone.now();family.save()
    draft.base_version=release.number;draft.revision+=1;draft.save()
    FontPublishOperation.objects.create(family=family,key=key,digest=request_hash,release=release)
    FontAudit.objects.create(family=family,actor=actor,action='publish',detail={'version':release.number})
    return release

def access(request,family):
    from billing.access import describe
    result=describe(request,'font',family.pk)
    personal=FontPersonalEntry.objects.filter(user=request.user,family=family).first()
    if personal and personal.free_claimed:
        result['access'].update(can_use=True,reason='claimed',permanently_owned=True,can_redeem=False)
    # An inactive offer is not an invitation to new membership/free acquisition.
    offer=ContentOffer.objects.filter(target_kind='font',target_id=family.pk,state='active').exists()
    if not offer and not result['access']['permanently_owned']:
        result['access'].update(can_use=False,can_redeem=False,reason='unavailable')
    if not family.active and not result['access']['permanently_owned']:
        result['access'].update(can_use=False,can_redeem=False,reason='withdrawn')
    return result
