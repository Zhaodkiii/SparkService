"""Explicit-selection batch drafts. Preview is read-only; save is all-or-nothing."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from common.permissions import AdminCodePermission
from .views import AuthView
from .models import ContentOffer, ContentPolicyDraft, BillingAudit
from .catalog import public_contents
from .pricing import PolicyInput, publication_checks, save_draft, publish
from .services import digest
from .identity import BillingError


class BatchTarget(serializers.Serializer):
    target_kind=serializers.ChoiceField(choices=['template','sticker_library','font'])
    target_id=serializers.UUIDField()


class BatchInput(serializers.Serializer):
    items=BatchTarget(many=True, min_length=1, max_length=100)
    access_mode=serializers.ChoiceField(choices=['free','pro_only','diamond_only','pro_or_diamond'])
    diamond_price=serializers.IntegerField(min_value=1,max_value=1000000,allow_null=True,default=None)
    change_reason=serializers.CharField(max_length=500,allow_blank=False)
    overwrite_drafts=serializers.BooleanField(default=False)
    expected_preview_hash=serializers.CharField(required=False)
    def validate(self,data):
        keys=[(x['target_kind'],x['target_id']) for x in data['items']]
        if len(keys)!=len(set(keys)): raise serializers.ValidationError('选择的内容不能重复')
        diamond=data['access_mode'] in ('diamond_only','pro_or_diamond')
        if diamond != (data['diamond_price'] is not None): raise serializers.ValidationError('钻石解锁方式必须填写价格；其他方式不应填写钻石价格')
        return data


def plan(data, lock=False):
    result=[]; fingerprints=[]
    # The same deterministic lock order is used for every batch, including new offers.
    for item in sorted(data['items'],key=lambda x:(x['target_kind'],str(x['target_id']))):
        kind=item['target_kind'];key=item['target_id']
        qs=public_contents(kind)
        target=get_object_or_404(qs.select_for_update() if lock else qs,pk=key)
        offers=ContentOffer.objects.filter(target_kind=kind,target_id=key)
        offer=(offers.select_for_update() if lock else offers).first()
        current=offer.current_policy_revision if offer else None
        draft=ContentPolicyDraft.objects.filter(offer=offer).first() if offer else None
        draft_hash=digest(draft.body) if draft else None
        base=dict(expected_revision=current.revision if current else 0,access_mode=current.access_mode if current else None,
                  diamond_price=current.diamond_price if current else None,currency_code=current.currency_code if current else None,
                  pro_entitlement_key=current.pro_entitlement_key if current else None,
                  bundled_grants=current.bundled_grants if current else [],terms_version=current.terms_version if current else 'content-personal-v1',change_reason='')
        fingerprints.append(dict(kind=kind,id=str(key),offer=str(offer.pk) if offer else None,base=base,draft_hash=draft_hash))
        row=dict(target_kind=kind,target_id=str(key),title=target.title,current=base,draft=draft.body if draft else None,previous=draft.body if draft else base)
        if draft and not data['overwrite_drafts']:
            result.append(dict(**row,skipped=True,skip_reason='已有草稿，默认保留',blockers=[]));continue
        if draft and draft.expected_base_revision!=base['expected_revision']:
            raise BillingError('PRICE_CHANGED',f'「{target.title}」存在过期草稿，请先单独对比并处理')
        source=draft.body if draft else base
        body={**source,'expected_revision':base['expected_revision'],'access_mode':data['access_mode'],
              'diamond_price':data['diamond_price'],'currency_code':'DIAMOND' if data['diamond_price'] is not None else None,
              'pro_entitlement_key':'member' if data['access_mode'] in ('pro_only','pro_or_diamond') else None,
              'change_reason':data['change_reason']}
        form=PolicyInput(data=body)
        if not form.is_valid(): raise serializers.ValidationError({'content':target.title,'errors':form.errors})
        body=form.validated_data
        candidate=offer or ContentOffer(target_kind=kind,target_id=key,title=target.title)
        result.append(dict(**row,skipped=False,body=body,blockers=publication_checks(candidate,body)))
    fingerprint=digest({'items':fingerprints,'access_mode':data['access_mode'],'diamond_price':data['diamond_price'],
                        'change_reason':data['change_reason'],'overwrite_drafts':data['overwrite_drafts']})
    return result,fingerprint


class BatchPricing(AuthView):
    permission_classes=[AdminCodePermission]
    @property
    def required_permission_code(self):
        return 'billing.publish_pricing' if self.kwargs.get('action') == 'publish' else 'billing.change_pricing_draft'
    def post(self,request,action):
        if action not in ('preview','save','publish'):
            from rest_framework.exceptions import NotFound
            raise NotFound('不支持的批量操作')
        form=BatchInput(data=request.data);form.is_valid(raise_exception=True);data=form.validated_data
        if action == 'publish':
            from backoffice.rbac import has_permission_code
            from rest_framework.exceptions import PermissionDenied
            if not request.user.is_superuser and not has_permission_code(request.user.id, 'billing.change_pricing_draft'):
                raise PermissionDenied('批量配置并发布需要草稿编辑和发布权限')
        if action=='preview':
            items,key=plan(data)
            return Response(dict(items=items,preview_hash=key,save_count=sum(not r['skipped'] for r in items),skipped_count=sum(r['skipped'] for r in items)))
        with transaction.atomic():
            items,key=plan(data,lock=True)
            if data.get('expected_preview_hash')!=key:
                raise BillingError('BATCH_CHANGED','所选内容、线上策略或草稿已变化，请重新预览后保存')
            if action == 'publish':
                if any(row['skipped'] for row in items):
                    raise BillingError('BATCH_SKIPPED', '存在已跳过的草稿，请选择替换已有草稿或移除这些内容后重新预览')
                if any(row['blockers'] for row in items):
                    raise BillingError('BATCH_BLOCKED', '部分内容未通过发布检查，请解决限制后重新预览；本次没有发布任何内容')
            saved=[]
            published=[]
            for row in items:
                if row['skipped']: continue
                offer,created=ContentOffer.objects.get_or_create(target_kind=row['target_kind'],target_id=row['target_id'],defaults={'title':row['title'],'state':'draft'})
                if created: BillingAudit.objects.create(actor=request.user,action='create_content_offer',target=str(offer.pk),detail={'target_kind':row['target_kind'],'target_id':row['target_id']})
                current_draft=ContentPolicyDraft.objects.filter(offer=offer).first()
                save_draft(offer.pk,{**row['body'],'expected_draft_hash':digest(current_draft.body) if current_draft else None},request.user)
                saved.append(str(offer.pk))
                if action == 'publish':
                    policy = publish(offer.pk, request.user, digest(row['body']))
                    published.append(dict(offer_id=str(offer.pk), title=row['title'], revision=policy.revision))
            if action == 'publish':
                BillingAudit.objects.create(actor=request.user, action='batch_publish_pricing', target='content-offers', detail={'offer_ids':saved,'reason':data['change_reason'],'preview_hash':key})
                return Response(dict(published_count=len(published), items=published))
            BillingAudit.objects.create(actor=request.user,action='batch_save_pricing_drafts',target='content-offers',detail={'offer_ids':saved,'reason':data['change_reason'],'preview_hash':key})
            return Response(dict(saved_count=len(saved),skipped_count=len(items)-len(saved),offer_ids=saved))
