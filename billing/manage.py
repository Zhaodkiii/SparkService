from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from common.permissions import AdminCodePermission
from .views import AuthView
from .models import ContentOffer,ContentPolicyDraft,ContentOwnership,RedemptionOrder,RedemptionQuote
from . import pricing

def offer_json(offer):
    from .services import digest
    p = offer.current_policy_revision
    draft = getattr(offer, 'contentpolicydraft', None)
    stale = bool(draft and draft.expected_base_revision != (p.revision if p else 0))
    blockers = pricing.publication_checks(offer, draft.body) if draft else []
    return dict(id=str(offer.pk), target_kind=offer.target_kind, target_id=str(offer.target_id), title=offer.title,
                state=offer.state, revision=p.revision if p else 0, access_mode=p.access_mode if p else None,
                diamond_price=p.diamond_price if p else None, currency_code=p.currency_code if p else None,
                pro_entitlement_key=p.pro_entitlement_key if p else None, bundled_grants=p.bundled_grants if p else [],
                terms_version=p.terms_version if p else 'content-personal-v1',
                draft=draft.body if draft else None, stale_draft=stale,
                draft_hash=digest(draft.body) if draft else None,
                workflow_status='blocked' if blockers else 'draft' if draft else 'active' if p else 'unconfigured', blockers=blockers,
                updated_at=draft.updated_at if draft else p.created_at if p else offer.created_at,
                updated_by=draft.actor.get_username() if draft else p.published_by.get_username() if p and p.published_by else '系统',
                published_at=p.created_at if p else None)


def bundle_options(grants):
    from material_library.models import MaterialLibrary
    import uuid
    ids=[]
    for grant in grants:
        try: ids.append(uuid.UUID(str(grant.get('target_id'))))
        except (ValueError, TypeError): pass
    titles={str(x.pk):x.title for x in MaterialLibrary.objects.filter(pk__in=ids)}
    return [{'value':str(key),'label':titles.get(str(key), '素材已不可用 · '+str(key))} for key in dict.fromkeys(ids)]


class ManageCatalog(AuthView):
    permission_classes = [AdminCodePermission]
    required_permission_code = 'billing.view_pricing'
    def get(self, request):
        from .catalog import catalog_page
        return Response(catalog_page(request.query_params))


class ManageOffers(AuthView):
    permission_classes=[AdminCodePermission]
    @property
    def required_permission_code(self):
        return 'billing.change_pricing_draft' if self.request.method=='POST' else 'billing.view_pricing'
    def get(self,request):
        from .catalog import CatalogQuery
        from django.db.models import Q
        import uuid
        form=CatalogQuery(data=request.query_params);form.is_valid(raise_exception=True);data=form.validated_data
        qs=ContentOffer.objects.select_related('current_policy_revision__published_by','contentpolicydraft__actor').order_by('title','id')
        if data['target_kind']: qs=qs.filter(target_kind=data['target_kind'])
        if request.query_params.get('target_id'):
            from rest_framework import serializers
            qs=qs.filter(target_id=serializers.UUIDField().run_validation(request.query_params['target_id']))
        if data['q']:
            search=Q(title__icontains=data['q'])
            try: search |= Q(target_id=uuid.UUID(data['q']))
            except ValueError: pass
            qs=qs.filter(search)
        if data['access_mode']: qs=qs.filter(current_policy_revision__access_mode=data['access_mode'])
        total=qs.count();start=(data['page']-1)*data['page_size']
        from django.conf import settings
        return Response({'items':[offer_json(x) for x in qs[start:start+data['page_size']]],'total':total,'page':data['page'],'page_size':data['page_size'],'test_policy_changes_enabled':settings.BILLING_TEST_POLICY_CHANGES_ENABLED})

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
            target=get_object_or_404(Template,pk=data['target_id'],audience='public',deleted_at__isnull=True)
        elif data['target_kind']=='font':
            from font_library.models import FontFamily
            target=get_object_or_404(FontFamily,pk=data['target_id'])
        else:
            from material_library.models import MaterialLibrary
            target=get_object_or_404(MaterialLibrary,pk=data['target_id'],deleted_at__isnull=True)
            if target.template_id and target.template.audience!='public':
                raise serializers.ValidationError('私有定制素材不能配置公共售价')
        offer,created=ContentOffer.objects.get_or_create(**data,defaults={'title':target.title,'state':'draft'})
        if created: BillingAudit.objects.create(actor=request.user,action='create_content_offer',target=str(offer.pk),detail={'target_kind':data['target_kind'],'target_id':str(target.pk)})
        return Response(offer_json(offer),status=201 if created else 200)

class ManagePolicy(AuthView):
    permission_classes=[AdminCodePermission]
    def check_action(self, action, allowed):
        if action not in allowed:
            from rest_framework.exceptions import NotFound
            raise NotFound('不支持的策略操作')
    @property
    def required_permission_code(self):
        if self.request.method == 'GET' or (self.request.method == 'POST' and self.kwargs.get('action') == 'publish-preview'): return 'billing.view_pricing'
        return 'billing.publish_pricing' if self.kwargs.get('action')=='publish' else 'billing.change_pricing_draft'
    def get(self,request,pk,action):
        self.check_action(action, ['draft', 'history'])
        from .services import digest
        offer=get_object_or_404(ContentOffer,pk=pk)
        if action=='history':
            from .models import BillingAudit
            audits={x.detail.get('new_revision'): x.detail.get('reason','') for x in BillingAudit.objects.filter(target=str(offer.pk),action='publish_pricing')}
            return Response({'items':[dict(revision=p.revision,access_mode=p.access_mode,diamond_price=p.diamond_price,bundled_grants=p.bundled_grants,terms_version=p.terms_version,created_at=p.created_at,published_by=p.published_by.get_username() if p.published_by else '系统',change_reason=audits.get(p.revision,'')) for p in offer.policies.select_related('published_by').order_by('-revision')]})
        draft=ContentPolicyDraft.objects.filter(offer=offer).first()
        current_revision=offer.current_policy_revision.revision if offer.current_policy_revision_id else 0
        stale=bool(draft and draft.expected_base_revision!=current_revision)
        return Response({'offer':offer_json(offer),'draft':draft.body if draft and not stale else None,'stale_draft':stale,'stale_body':draft.body if stale else None,'bundle_options':bundle_options((draft.body.get('bundled_grants',[]) if draft else []) + (offer.current_policy_revision.bundled_grants if offer.current_policy_revision_id else [])),'draft_hash':digest(draft.body) if draft else None})
    def patch(self,request,pk,action):
        self.check_action(action, ['draft'])
        from .services import digest
        get_object_or_404(ContentOffer,pk=pk)
        draft=pricing.save_draft(pk,request.data,request.user)
        return Response({'draft':draft.body,'draft_hash':digest(draft.body)})
    def delete(self,request,pk,action):
        self.check_action(action, ['draft'])
        from django.db import transaction
        from .models import BillingAudit
        from .services import digest
        from .identity import BillingError
        with transaction.atomic():
            offer=get_object_or_404(ContentOffer.objects.select_for_update(),pk=pk)
            draft=ContentPolicyDraft.objects.filter(offer=offer).first()
            if draft and request.data.get('expected_draft_hash') != digest(draft.body):
                raise BillingError('DRAFT_CHANGED','草稿已变化，请重新加载后再放弃')
            if draft:
                BillingAudit.objects.create(actor=request.user,action='discard_pricing_draft',target=str(pk),detail=draft.body)
                draft.delete()
        return Response({'discarded':True})
    def post(self,request,pk,action):
        self.check_action(action, ['publish', 'publish-preview'])
        offer=get_object_or_404(ContentOffer,pk=pk)
        if action=='publish':
            p=pricing.publish(pk,request.user,request.data.get('expected_draft_hash'))
            return Response({'revision':p.revision,'published_at':p.created_at})
        from .services import target_available, digest
        draft=get_object_or_404(ContentPolicyDraft,offer=offer)
        blockers=pricing.publication_checks(offer,draft.body)
        owned=ContentOwnership.objects.filter(target_kind=offer.target_kind,target_id=offer.target_id,state='active').values('identity').distinct().count()
        pending=RedemptionOrder.objects.filter(offer=offer).exclude(status__in=['fulfilled','rejected','compensated']).count()
        return Response({'draft':draft.body,'draft_hash':digest(draft.body),'deliverable':target_available(offer),
                         'can_publish':not blockers,'blockers':blockers,'current':offer_json(offer),'owned_users':owned,'pending_orders':pending,
                         'warnings':['永久解锁用户保留原许可；此数量不包含仅通过免费或 Pro 权益使用的用户。',
                                     '待处理订单会按执行阶段重新校验价格；尚未扣钻的旧价格订单可能被拒绝，已确认扣钻订单按原单处理。'] +
                                    (['字体策略可先发布；字体内容正式发布前仍不可兑换。'] if offer.target_kind=='font' and not target_available(offer) else [])})

class ManagePackages(AuthView):
    permission_classes=[AdminCodePermission]
    required_permission_code='billing.publish_pricing'
    def get(self,request):
        from .models import CustomizationPackageRevision
        return Response({'items':list(CustomizationPackageRevision.objects.select_related('package').values('id','package__title','package__code','revision','standard_diamonds','pro_diamonds','included_pages','max_photos','included_revision_rounds','lead_workdays','terms_version'))})
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
            title=data.pop('title')
            package,_=CustomizationPackage.objects.get_or_create(code=data.pop('code'),defaults={'title':title})
            package=CustomizationPackage.objects.select_for_update().get(pk=package.pk)
            expected=data.pop('expected_revision')
            if (package.current_revision.revision if package.current_revision_id else 0)!=expected:
                from .identity import BillingError
                raise BillingError('PRICE_CHANGED')
            revision=CustomizationPackageRevision.objects.create(package=package,revision=expected+1,**data)
            package.title=title;package.current_revision=revision;package.state='active';package.save()
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
    required_permission_code='billing.view_transactions'
    def get(self,request):
        from .operations_admin import list_operations
        return Response(list_operations(request.query_params))

class ManageCompensation(AuthView):
    permission_classes=[AdminCodePermission]
    required_permission_code='billing.resolve_refund'
    def post(self,request,pk):
        from .refunds import compensate
        from .services import process
        operation=compensate(pk,request.user,request.data.get('reason',''))
        process(operation.pk);operation.refresh_from_db()
        return Response({'operation_id':str(operation.pk),'state':operation.state},status=200 if operation.state=='succeeded' else 202)
