from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from common.permissions import AdminCodePermission
from .views import AuthView
from .models import ContentOffer,ContentPolicyDraft,ContentOwnership,RedemptionOrder,RedemptionQuote
from . import pricing

def offer_json(offer):
    p=offer.current_policy_revision
    return dict(id=str(offer.pk),target_kind=offer.target_kind,target_id=str(offer.target_id),title=offer.title,state=offer.state,revision=p.revision if p else 0,access_mode=p.access_mode if p else None,diamond_price=p.diamond_price if p else None,currency_code=p.currency_code if p else None,pro_entitlement_key=p.pro_entitlement_key if p else None)

class ManageOffers(AuthView):
    permission_classes=[AdminCodePermission]
    @property
    def required_permission_code(self):
        return 'billing.change_pricing_draft' if self.request.method=='POST' else 'billing.view_pricing'
    def get(self,request):
        qs=ContentOffer.objects.select_related('current_policy_revision').order_by('title')
        for key in ['target_kind','target_id']:
            if request.query_params.get(key): qs=qs.filter(**{key:request.query_params[key]})
        from django.conf import settings
        return Response({'items':[offer_json(x) for x in qs[:500]],'test_policy_changes_enabled':settings.BILLING_TEST_POLICY_CHANGES_ENABLED})

    def post(self,request):
        from rest_framework import serializers
        from .models import BillingAudit
        class Input(serializers.Serializer):
            target_kind=serializers.ChoiceField(choices=['template','sticker_library','font'])
            target_id=serializers.UUIDField()
        form=Input(data=request.data);form.is_valid(raise_exception=True)
        data=form.validated_data
        if data['target_kind']=='template':
            from diary_presets.models import Template
            target=get_object_or_404(Template,pk=data['target_id'],audience='public')
        elif data['target_kind']=='font':
            from font_library.models import FontFamily
            target=get_object_or_404(FontFamily,pk=data['target_id'])
        else:
            from material_library.models import MaterialLibrary
            target=get_object_or_404(MaterialLibrary,pk=data['target_id'])
            if target.template_id and target.template.audience!='public':
                raise serializers.ValidationError('私有定制素材不能配置公共售价')
        offer,created=ContentOffer.objects.get_or_create(**data,defaults={'title':target.title,'state':'draft'})
        if created: BillingAudit.objects.create(actor=request.user,action='create_content_offer',target=str(offer.pk),detail={'target_kind':data['target_kind'],'target_id':str(target.pk)})
        return Response(offer_json(offer),status=201 if created else 200)

class ManagePolicy(AuthView):
    permission_classes=[AdminCodePermission]
    @property
    def required_permission_code(self):
        return 'billing.publish_pricing' if self.kwargs.get('action')=='publish' else 'billing.change_pricing_draft'
    def get(self,request,pk,action):
        offer=get_object_or_404(ContentOffer,pk=pk)
        if action=='history': return Response({'items':list(offer.policies.values('revision','access_mode','diamond_price','created_at'))})
        draft=ContentPolicyDraft.objects.filter(offer=offer).first()
        current_revision=offer.current_policy_revision.revision if offer.current_policy_revision_id else 0
        stale=bool(draft and draft.expected_base_revision!=current_revision)
        return Response({'offer':offer_json(offer),'draft':draft.body if draft and not stale else None,'stale_draft':stale})
    def patch(self,request,pk,action):
        get_object_or_404(ContentOffer,pk=pk)
        draft=pricing.save_draft(pk,request.data,request.user)
        return Response({'draft':draft.body})
    def post(self,request,pk,action):
        offer=get_object_or_404(ContentOffer,pk=pk)
        if action=='publish':
            p=pricing.publish(pk,request.user,request.data.get('expected_draft_hash'));return Response({'revision':p.revision})
        from .services import target_available
        draft=get_object_or_404(ContentPolicyDraft,offer=offer)
        from .services import digest
        current_revision=offer.current_policy_revision.revision if offer.current_policy_revision_id else 0
        if draft.expected_base_revision!=current_revision:
            from .identity import BillingError
            raise BillingError('PRICE_CHANGED','草稿基于旧策略版本，请刷新后重新编辑并保存')
        return Response({'draft':draft.body,'draft_hash':digest(draft.body),'deliverable':target_available(offer),'current':offer_json(offer),'owned_users':ContentOwnership.objects.filter(target_kind=offer.target_kind,target_id=offer.target_id,state='active').values('identity').distinct().count(),'pending_orders':RedemptionOrder.objects.filter(offer=offer).exclude(status__in=['fulfilled','rejected','compensated']).count()})

class ManagePackages(AuthView):
    permission_classes=[AdminCodePermission]
    required_permission_code='billing.publish_pricing'
    def get(self,request):
        from .models import CustomizationPackageRevision
        return Response({'items':list(CustomizationPackageRevision.objects.select_related('package').values('id','package__title','package__code','revision','standard_diamonds','pro_diamonds','included_pages','max_photos','included_revision_rounds','lead_workdays'))})
    def post(self,request):
        from django.db import transaction
        from rest_framework import serializers
        from .models import CustomizationPackage,CustomizationPackageRevision,BillingAudit
        class PackageInput(serializers.Serializer):
            code=serializers.SlugField(max_length=64)
            title=serializers.CharField(max_length=120)
            expected_revision=serializers.IntegerField(min_value=0)
            standard_diamonds=serializers.IntegerField(min_value=1,max_value=1000000)
            pro_diamonds=serializers.IntegerField(min_value=1,max_value=1000000,allow_null=True,default=None)
            included_pages=serializers.IntegerField(min_value=1,max_value=100)
            max_photos=serializers.IntegerField(min_value=1,max_value=30)
            included_revision_rounds=serializers.IntegerField(min_value=0,max_value=10)
            lead_workdays=serializers.IntegerField(min_value=1,max_value=90)
            terms_version=serializers.CharField(max_length=64)
        form=PackageInput(data=request.data);form.is_valid(raise_exception=True);data=form.validated_data
        if data['pro_diamonds'] is not None and data['pro_diamonds']>data['standard_diamonds']: raise serializers.ValidationError('Pro 价不得高于普通价')
        with transaction.atomic():
            package,_=CustomizationPackage.objects.get_or_create(code=data.pop('code'),defaults={'title':data.pop('title')})
            package=CustomizationPackage.objects.select_for_update().get(pk=package.pk)
            expected=data.pop('expected_revision')
            if (package.current_revision.revision if package.current_revision_id else 0)!=expected:
                from .identity import BillingError
                raise BillingError('PRICE_CHANGED')
            revision=CustomizationPackageRevision.objects.create(package=package,revision=expected+1,**data)
            package.current_revision=revision;package.state='active';package.save()
            BillingAudit.objects.create(actor=request.user,action='publish_custom_package',target=str(package.pk),detail={'revision':revision.revision})
        return Response({'id':str(revision.pk),'revision':revision.revision},status=201)

class ManageCustomizationQuote(AuthView):
    permission_classes=[AdminCodePermission]
    required_permission_code='billing.publish_pricing'
    def get(self,request,pk):
        from diary_customizations.models import Request
        from .models import CustomizationQuote,CustomizationFunding
        obj=get_object_or_404(Request,pk=pk,deleted_at__isnull=True)
        return Response({'quotes':list(CustomizationQuote.objects.filter(request=obj).order_by('-revision').values('id','revision','standard_diamonds','pro_diamonds','scope_snapshot','expires_at','expected_request_revision')),'fundings':list(CustomizationFunding.objects.filter(request=obj).order_by('-created_at').values('id','amount','status','quote_id','identity__wallet_domain'))})
    def post(self,request,pk):
        from rest_framework import serializers
        from .customization import issue_quote
        package_id=serializers.UUIDField().run_validation(request.data.get('package_revision_id'))
        quote=issue_quote(pk,package_id,request.user)
        return Response({'quote_id':str(quote.pk),'revision':quote.revision},status=201)

class ManageOperations(AuthView):
    permission_classes=[AdminCodePermission]
    required_permission_code='billing.view_pricing'
    def get(self,request):
        from .models import WalletOperation,ReconciliationCase
        return Response({'items':list(WalletOperation.objects.order_by('-created_at').values('id','identity_id','order_id','funding_id','kind','delta','state','attempt_count','created_at')[:200]),'cases':list(ReconciliationCase.objects.filter(status='open').values('id','identity_id','operation_id','kind','created_at')[:100])})

class ManageCompensation(AuthView):
    permission_classes=[AdminCodePermission]
    required_permission_code='billing.resolve_refund'
    def post(self,request,pk):
        from .refunds import compensate
        from .services import process
        operation=compensate(pk,request.user,request.data.get('reason',''))
        process(operation.pk);operation.refresh_from_db()
        return Response({'operation_id':str(operation.pk),'state':operation.state},status=200 if operation.state=='succeeded' else 202)
