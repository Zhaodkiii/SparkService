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
    actual=offer.current_policy_revision.revision if offer.current_policy_revision_id else 0
    if data['expected_revision']!=actual: raise BillingError('PRICE_CHANGED','策略已更新，请刷新')
    if data['bundled_grants'] and offer.target_kind!='template': raise BillingError('INVALID_BUNDLE')
    draft,_=ContentPolicyDraft.objects.update_or_create(offer=offer,defaults=dict(expected_base_revision=actual,body=data,actor=actor))
    BillingAudit.objects.create(actor=actor,action='save_pricing_draft',target=str(offer.pk),detail=data)
    return draft

@transaction.atomic
def publish(offer_id,actor,expected_draft_hash):
    offer=ContentOffer.objects.select_for_update().get(pk=offer_id)
    draft=ContentPolicyDraft.objects.filter(offer=offer).first()
    if not draft: raise BillingError('DRAFT_NOT_FOUND','草稿已发布或不存在，请刷新后重新编辑')
    if expected_draft_hash!=digest(draft.body): raise BillingError('DRAFT_CHANGED','收费草稿已变化，请重新查看影响后发布')
    previous=offer.current_policy_revision
    if (previous.revision if previous else 0)!=draft.expected_base_revision: raise BillingError('PRICE_CHANGED','草稿基于旧策略版本，请刷新后重新编辑并保存')
    if not target_available(offer): raise BillingError('CONTENT_UNAVAILABLE')
    form=PolicyInput(data=draft.body);form.is_valid(raise_exception=True);body=form.validated_data
    if body['access_mode'] in ('diamond_only','pro_or_diamond') and not settings.DIAMOND_REDEMPTION_ENABLED:
        raise BillingError('SALES_DISABLED','钻石兑换验收完成并开放后才能发布收费策略')
    if body['access_mode'] in ('pro_only','pro_or_diamond') and not (settings.MEMBERSHIP_SALES_ENABLED or (settings.BILLING_TEST_POLICY_CHANGES_ENABLED and settings.BILLING_SANDBOX_SALES_ENABLED)):
        raise BillingError('SALES_DISABLED','会员服务尚未开放')
    if previous and previous.access_mode in ('free','pro_only','pro_or_diamond') and body['access_mode']!=previous.access_mode and not settings.BILLING_TEST_POLICY_CHANGES_ENABLED:
        raise BillingError('MIGRATION_REQUIRED','已发布免费或 Pro 范围的变更需先制定权益迁移方案')
    policy=ContentPolicyRevision.objects.create(offer=offer,revision=draft.expected_base_revision+1,access_mode=body['access_mode'],diamond_price=body['diamond_price'],currency_code=body['currency_code'],pro_entitlement_key=body['pro_entitlement_key'],bundled_grants=body['bundled_grants'],terms_version=body['terms_version'],published_by=actor,content_scope_snapshot={'target_kind':offer.target_kind,'target_id':str(offer.target_id),'scope':offer.ownership_scope})
    offer.current_policy_revision=policy;offer.state='active';offer.save()
    BillingAudit.objects.create(actor=actor,action='publish_pricing',target=str(offer.pk),detail={'old_revision':draft.expected_base_revision,'new_revision':policy.revision,'reason':body['change_reason']})
    draft.delete()
    return policy
