from billing.flags import sales_enabled
from django.db import transaction
from django.conf import settings
from rest_framework import serializers
from .identity import BillingError
from .models import ContentOffer,ContentPolicyDraft,ContentPolicyRevision,BillingAudit,ContentOwnership,RedemptionOrder,RedemptionQuote
from .services import target_available,digest

class PolicyInput(serializers.Serializer):
    expected_revision=serializers.IntegerField(min_value=0)
    access_mode=serializers.ChoiceField(choices=['free','pro_only','diamond_only','pro_or_diamond'])
    diamond_price=serializers.IntegerField(min_value=1,max_value=1000000,allow_null=True,required=False,default=None)
    currency_code=serializers.ChoiceField(choices=['DIAMOND'],allow_null=True,required=False,default=None)
    pro_entitlement_key=serializers.ChoiceField(choices=['member'],allow_null=True,required=False,default=None)
    bundled_grants=serializers.ListField(child=serializers.DictField(),max_length=30,default=list)
    terms_version=serializers.CharField(max_length=64)
    change_reason=serializers.CharField(max_length=500,error_messages={'required':'请填写变更说明','blank':'请填写变更说明，说明本次调整的原因','max_length':'变更说明最多 500 字'})
    def validate(self,data):
        diamonds=data['access_mode'] in ('diamond_only','pro_or_diamond')
        pro=data['access_mode'] in ('pro_only','pro_or_diamond')
        if diamonds != (data['diamond_price'] is not None) or diamonds != (data['currency_code']=='DIAMOND'):
            raise serializers.ValidationError('钻石模式必须有正整数价格和 DIAMOND；其他模式不得设置价格')
        if pro != (data['pro_entitlement_key']=='member'): raise serializers.ValidationError('Pro 模式必须明确 member 权益')
        normalized=[]
        for grant in data['bundled_grants']:
            if set(grant)!={'target_kind','target_id'} or grant['target_kind']!='sticker_library': raise serializers.ValidationError('只支持模板附赠明确的贴纸包')
            target=serializers.UUIDField().run_validation(grant['target_id'])
            item=ContentOffer.objects.filter(target_kind='sticker_library',target_id=target,state='active').first()
            if not item or not target_available(item): raise serializers.ValidationError('附赠贴纸包不可交付')
            normalized.append(dict(target_kind='sticker_library',target_id=str(target)))
        data['bundled_grants']=normalized
        return data

@transaction.atomic
def save_draft(offer_id,body,actor):
    offer=ContentOffer.objects.select_for_update().get(pk=offer_id)
    form=PolicyInput(data=body);form.is_valid(raise_exception=True);data=form.validated_data
    existing = ContentPolicyDraft.objects.filter(offer=offer).first()
    if 'expected_draft_hash' in body and body['expected_draft_hash'] != (digest(existing.body) if existing else None):
        raise BillingError('DRAFT_CHANGED', '其他操作员已修改草稿，请重新加载并对比后保存')
    actual=offer.current_policy_revision.revision if offer.current_policy_revision_id else 0
    if data['expected_revision']!=actual: raise BillingError('PRICE_CHANGED','策略已更新，请刷新')
    if data['bundled_grants'] and offer.target_kind!='template': raise BillingError('INVALID_BUNDLE')
    draft,_=ContentPolicyDraft.objects.update_or_create(offer=offer,defaults=dict(expected_base_revision=actual,body=data,actor=actor))
    BillingAudit.objects.create(actor=actor,action='save_pricing_draft',target=str(offer.pk),detail=data)
    return draft

def publication_checks(offer, body):
    blockers = []
    def block(code, message, destination='/billing'):
        blockers.append(dict(code=code, message=message, destination=destination))
    current = offer.current_policy_revision
    if body.get('expected_revision') != (current.revision if current else 0):
        block('PRICE_CHANGED', '草稿基于旧策略版本，请对比最新策略后重新保存')
    form = PolicyInput(data=body)
    if not form.is_valid():
        block('INVALID_POLICY', '；'.join(str(message) for messages in form.errors.values() for message in (messages if isinstance(messages, list) else [messages])))
    if offer.target_kind == 'font':
        from font_library.models import FontFamily, FontDraft
        from font_library.services import issues
        font = FontFamily.objects.filter(pk=offer.target_id).first()
        draft = FontDraft.objects.filter(family=font).first() if font else None
        if not font or not draft:
            block('CONTENT_UNAVAILABLE', '字体或字体草稿不存在，请先完善字体内容', '/content/fonts')
        else:
            problems, _ = issues(font, draft.content, policy=False)
            if problems:
                block('CONTENT_UNAVAILABLE', '；'.join(problems), '/content/fonts')
    elif not target_available(offer):
        block('CONTENT_UNAVAILABLE', '内容尚未发布、已停用或不可交付，请先检查内容状态', '/content/templates' if offer.target_kind == 'template' else '/content/stickers')
    mode = body.get('access_mode')
    if mode in ('diamond_only', 'pro_or_diamond') and not sales_enabled('DIAMOND_REDEMPTION_ENABLED'):
        block('SALES_DISABLED', '钻石兑换尚未开放，请联系服务管理员完成验收并开放')
    if mode in ('pro_only', 'pro_or_diamond') and not (sales_enabled('MEMBERSHIP_SALES_ENABLED') or (settings.BILLING_TEST_POLICY_CHANGES_ENABLED and settings.BILLING_SANDBOX_SALES_ENABLED)):
        block('SALES_DISABLED', '会员服务尚未开放，请联系服务管理员')
    # Compare use rights without a permanent purchase. Existing ownerships are
    # preserved independently; adding/removing a purchase option is not a loss
    # of the free or membership scope.
    included_users = {
        'free': {'ordinary', 'pro'},
        'pro_only': {'pro'},
        'pro_or_diamond': {'pro'},
        'diamond_only': set(),
    }
    if current and mode in included_users and not settings.BILLING_TEST_POLICY_CHANGES_ENABLED:
        removed = included_users.get(current.access_mode, set()) - included_users[mode]
        if removed:
            affected = '普通用户的免费使用权益' if 'ordinary' in removed else 'Pro 会员的免额外付费使用权益'
            block('MIGRATION_REQUIRED', f'本次调整会收回{affected}，暂不支持直接发布。请保留原有免费或 Pro 使用范围；如确需收回，需先完成老用户权益处理。已永久解锁的许可不受影响。')
    return blockers


@transaction.atomic
def publish(offer_id,actor,expected_draft_hash):
    offer=ContentOffer.objects.select_for_update().get(pk=offer_id)
    draft=ContentPolicyDraft.objects.filter(offer=offer).first()
    if not draft: raise BillingError('DRAFT_NOT_FOUND','草稿已发布或不存在，请刷新后重新编辑')
    if expected_draft_hash!=digest(draft.body): raise BillingError('DRAFT_CHANGED','收费草稿已变化，请重新查看影响后发布')
    previous=offer.current_policy_revision
    if (previous.revision if previous else 0)!=draft.expected_base_revision: raise BillingError('PRICE_CHANGED','草稿基于旧策略版本，请刷新后重新编辑并保存')
    blockers = publication_checks(offer, draft.body)
    if blockers:
        first = blockers[0]
        raise BillingError(first['code'], first['message'])
    form=PolicyInput(data=draft.body);form.is_valid(raise_exception=True);body=form.validated_data
    policy=ContentPolicyRevision.objects.create(offer=offer,revision=draft.expected_base_revision+1,access_mode=body['access_mode'],diamond_price=body['diamond_price'],currency_code=body['currency_code'],pro_entitlement_key=body['pro_entitlement_key'],bundled_grants=body['bundled_grants'],terms_version=body['terms_version'],published_by=actor,content_scope_snapshot={'target_kind':offer.target_kind,'target_id':str(offer.target_id),'scope':offer.ownership_scope})
    offer.current_policy_revision=policy;offer.state='active';offer.save()
    BillingAudit.objects.create(actor=actor,action='publish_pricing',target=str(offer.pk),detail={'old_revision':draft.expected_base_revision,'new_revision':policy.revision,'reason':body['change_reason']})
    draft.delete()
    return policy
