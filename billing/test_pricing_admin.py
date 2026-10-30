import uuid
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from .models import ContentOffer,ContentPolicyRevision,ContentPolicyDraft,BillingAudit
from .manage import ManageCatalog,ManageOffers,ManagePolicy
from .pricing import save_draft,publish,publication_checks
from .identity import BillingError
from .services import digest
from .catalog import catalog_page
from diary_presets.models import Series,Template,Version
from material_library.models import MaterialLibrary,LibraryVersion
from font_library.models import FontFamily

@override_settings(DIAMOND_REDEMPTION_ENABLED=True,MEMBERSHIP_SALES_ENABLED=True,BILLING_TEST_POLICY_CHANGES_ENABLED=False)
class PricingAdminTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('pricing-admin','admin@example.test','test')
        self.factory=APIRequestFactory()
        self.series=Series.objects.create(slug='test',title='测试系列')
        self.template=Template.objects.create(series=self.series,title='海边旅行')
        version=Version.objects.create(template=self.template,number=1,snapshot={})
        self.template.current=version;self.template.save()
        self.offer=ContentOffer.objects.create(target_kind='template',target_id=self.template.pk,title=self.template.title,state='active')
        self.policy=ContentPolicyRevision.objects.create(offer=self.offer,revision=1,access_mode='diamond_only',diamond_price=30,currency_code='DIAMOND',terms_version='original-v2')
        self.offer.current_policy_revision=self.policy;self.offer.save()
    def body(self,**changes):
        return dict(expected_revision=1,access_mode='diamond_only',diamond_price=50,currency_code='DIAMOND',pro_entitlement_key=None,bundled_grants=[],terms_version='original-v2',change_reason='调整主题包价格',**changes)
    def call(self,view,method='get',data=None,**kwargs):
        r=getattr(self.factory,method)('/',data or {},format='json');force_authenticate(r,user=self.user)
        return view.as_view()(r,**kwargs)
    def test_catalog_includes_unconfigured_and_real_filters(self):
        FontFamily.objects.create(title='旅行字体')
        MaterialLibrary.objects.create(title='旅行贴纸',library_type='sticker')
        private=Template.objects.create(series=self.series,title='私人旅行',audience='private',owner=self.user,customization_id=uuid.uuid4())
        MaterialLibrary.objects.create(template=private,title='私人素材',library_type='sticker')
        deleted=MaterialLibrary.objects.create(title='已删除旅行',library_type='sticker',deleted_at='2026-01-01T00:00:00Z')
        result=catalog_page({'q':'旅行'})
        self.assertEqual(result['total'],3)
        self.assertEqual(catalog_page({'status':'unconfigured'})['total'],2)
        self.assertEqual(catalog_page({'target_kind':'font'})['total'],1)
        self.assertEqual(catalog_page({'availability':'available'})['total'],1)
        self.assertEqual(catalog_page({'access_mode':'diamond_only'})['total'],1)
        self.assertEqual(catalog_page({'q':str(self.template.pk)})['items'][0]['id'],str(self.offer.pk))
        self.assertFalse(any(r['target_id']==str(deleted.pk) for r in result['items']))
    def test_more_than_500_contents_are_reachable(self):
        FontFamily.objects.bulk_create([FontFamily(title=f'字体 {n:04}') for n in range(505)])
        r=catalog_page({'target_kind':'font','page':26,'page_size':20})
        self.assertEqual(r['total'],505);self.assertEqual(len(r['items']),5)
        self.assertEqual(r['items'][-1]['title'],'字体 0504')
    def test_saved_draft_state_and_current_bundle_are_returned(self):
        self.policy.bundled_grants=[{'target_kind':'sticker_library','target_id':str(uuid.uuid4())}];self.policy.save()
        r=self.call(ManagePolicy,pk=self.offer.pk,action='draft')
        self.assertEqual(r.data['offer']['bundled_grants'],self.policy.bundled_grants)
        self.assertEqual(r.data['offer']['terms_version'],'original-v2')
        save_draft(self.offer.pk,self.body(),self.user)
        row=catalog_page({'status':'draft'})['items'][0]
        self.assertEqual(row['diamond_price'],30);self.assertEqual(row['draft']['diamond_price'],50)
        self.assertEqual(row['updated_by'],'pricing-admin')
    @override_settings(DIAMOND_REDEMPTION_ENABLED=False)
    def test_preview_and_publish_share_sales_blocker(self):
        save_draft(self.offer.pk,self.body(),self.user)
        r=self.call(ManagePolicy,'post',pk=self.offer.pk,action='publish-preview')
        self.assertFalse(r.data['can_publish']);self.assertTrue(r.data['deliverable'])
        self.assertEqual(r.data['blockers'][0]['code'],'SALES_DISABLED')
        with self.assertRaises(BillingError) as context: publish(self.offer.pk,self.user,r.data['draft_hash'])
        self.assertEqual(str(context.exception.detail['code']),'SALES_DISABLED')
    def test_migration_is_blocked_in_preview(self):
        self.policy.access_mode='free';self.policy.diamond_price=None;self.policy.currency_code=None;self.policy.save()
        self.offer.refresh_from_db()
        self.assertIn('MIGRATION_REQUIRED',[b['code'] for b in publication_checks(self.offer,self.body())])
    def test_concurrent_draft_edit_and_discard_are_protected(self):
        body=self.body();save_draft(self.offer.pk,{**body,'expected_draft_hash':None},self.user)
        with self.assertRaises(BillingError):save_draft(self.offer.pk,{**body,'expected_draft_hash':None},self.user)
        r=self.call(ManagePolicy,'delete',{'expected_draft_hash':'stale'},pk=self.offer.pk,action='draft')
        self.assertEqual(r.status_code,409);self.assertTrue(ContentPolicyDraft.objects.exists())
        r=self.call(ManagePolicy,'delete',{'expected_draft_hash':digest(ContentPolicyDraft.objects.get().body)},pk=self.offer.pk,action='draft')
        self.assertEqual(r.status_code,200);self.assertFalse(ContentPolicyDraft.objects.exists())
        self.assertTrue(BillingAudit.objects.filter(action='discard_pricing_draft').exists())
        self.offer.refresh_from_db();self.assertEqual(self.offer.current_policy_revision.diamond_price,30)
    def test_read_only_permission_can_inspect_but_not_edit(self):
        self.user.is_superuser=False;self.user.save()
        with patch('common.permissions.has_permission_code',side_effect=lambda uid,p:p=='billing.view_pricing'):
            self.assertEqual(self.call(ManagePolicy,pk=self.offer.pk,action='draft').status_code,200)
            self.assertEqual(self.call(ManagePolicy,pk=self.offer.pk,action='history').status_code,200)
            self.assertEqual(self.call(ManagePolicy,'patch',self.body(),pk=self.offer.pk,action='draft').status_code,403)
            self.assertEqual(self.call(ManagePolicy,'patch',self.body(),pk=self.offer.pk,action='publish-preview').status_code,403)
            self.assertEqual(self.call(ManagePolicy,'delete',{},pk=self.offer.pk,action='publish-preview').status_code,403)
            self.assertEqual(self.call(ManagePolicy,'post',{},pk=self.offer.pk,action='publish').status_code,403)
    def test_publish_history_and_stale_hash(self):
        draft=save_draft(self.offer.pk,self.body(),self.user)
        with self.assertRaises(BillingError):publish(self.offer.pk,self.user,'stale')
        p=publish(self.offer.pk,self.user,digest(draft.body))
        self.assertEqual(p.revision,2)
        history=self.call(ManagePolicy,pk=self.offer.pk,action='history').data['items']
        self.assertEqual(history[0]['revision'],2);self.assertEqual(history[0]['change_reason'],'调整主题包价格')
    def test_registration_rejects_private_content_and_reuses_existing(self):
        r=self.call(ManageOffers,'post',{'target_kind':'template','target_id':str(self.template.pk)})
        self.assertEqual(r.status_code,200);self.assertEqual(ContentOffer.objects.count(),1)
        private=Template.objects.create(series=self.series,title='私人',audience='private',owner=self.user,customization_id=uuid.uuid4())
        self.assertEqual(self.call(ManageOffers,'post',{'target_kind':'template','target_id':str(private.pk)}).status_code,404)
    def test_invalid_filters_are_rejected(self):
        self.assertEqual(self.call(ManageCatalog,data={'page':0}).status_code,400)

    @override_settings(DIAMOND_REDEMPTION_ENABLED=False)
    def test_blocked_filter_matches_shared_preflight(self):
        save_draft(self.offer.pk,self.body(),self.user)
        result=catalog_page({'status':'blocked'})
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['workflow_status'],'blocked')
        self.assertIn('SALES_DISABLED',[b['code'] for b in result['items'][0]['blockers']])

    @patch('font_library.services.issues',return_value=([], []))
    def test_first_font_policy_can_publish_before_content_release(self,_issues):
        from font_library.models import FontDraft
        font=FontFamily.objects.create(title='首次发布字体')
        FontDraft.objects.create(family=font,content={})
        offer=ContentOffer.objects.create(target_kind='font',target_id=font.pk,title=font.title)
        body={**self.body(),'expected_revision':0}
        draft=save_draft(offer.pk,body,self.user)
        preview=self.call(ManagePolicy,'post',pk=offer.pk,action='publish-preview').data
        self.assertFalse(preview['deliverable']);self.assertTrue(preview['can_publish'])
        self.assertEqual(publish(offer.pk,self.user,digest(draft.body)).revision,1)

    def test_bundle_survives_price_only_edit_end_to_end(self):
        library=MaterialLibrary.objects.create(title='附赠贴纸',library_type='sticker')
        library.current=LibraryVersion.objects.create(library=library,number=1,content={});library.save()
        gift=ContentOffer.objects.create(target_kind='sticker_library',target_id=library.pk,title=library.title,state='active')
        gift.current_policy_revision=ContentPolicyRevision.objects.create(offer=gift,revision=1,access_mode='free');gift.save()
        grants=[{'target_kind':'sticker_library','target_id':str(library.pk)}]
        self.policy.bundled_grants=grants;self.policy.save()
        current=self.call(ManagePolicy,pk=self.offer.pk,action='draft').data['offer']
        body={**self.body(),'bundled_grants':current['bundled_grants'],'terms_version':current['terms_version']}
        draft=save_draft(self.offer.pk,body,self.user)
        result=publish(self.offer.pk,self.user,digest(draft.body))
        self.assertEqual(result.bundled_grants,grants);self.assertEqual(result.terms_version,'original-v2')

    def test_all_access_mode_transitions_compare_included_rights(self):
        modes=['free','pro_only','pro_or_diamond','diamond_only']
        blocked={('free','pro_only'),('free','pro_or_diamond'),('free','diamond_only'),('pro_only','diamond_only'),('pro_or_diamond','diamond_only')}
        for old in modes:
            self.policy.access_mode=old
            self.policy.diamond_price=30 if old in ('diamond_only','pro_or_diamond') else None
            self.policy.currency_code='DIAMOND' if self.policy.diamond_price else None
            self.policy.pro_entitlement_key='member' if old in ('pro_only','pro_or_diamond') else None
            self.policy.save();self.offer.refresh_from_db()
            for new in modes:
                with self.subTest(previous=old,next=new):
                    body=self.body()
                    body.update(access_mode=new,diamond_price=50 if new in ('diamond_only','pro_or_diamond') else None,
                                currency_code='DIAMOND' if new in ('diamond_only','pro_or_diamond') else None,
                                pro_entitlement_key='member' if new in ('pro_only','pro_or_diamond') else None)
                    checks=publication_checks(self.offer,body)
                    self.assertEqual(any(b['code']=='MIGRATION_REQUIRED' for b in checks),(old,new) in blocked)

    def test_pro_to_free_preview_and_publish_succeed_without_migration(self):
        self.policy.access_mode='pro_only';self.policy.diamond_price=None;self.policy.currency_code=None
        self.policy.pro_entitlement_key='member';self.policy.save()
        body=self.body();body.update(access_mode='free',diamond_price=None,currency_code=None)
        draft=save_draft(self.offer.pk,body,self.user)
        preview=self.call(ManagePolicy,'post',pk=self.offer.pk,action='publish-preview').data
        self.assertTrue(preview['can_publish']);self.assertEqual(preview['blockers'],[])
        result=publish(self.offer.pk,self.user,digest(draft.body))
        self.assertEqual(result.access_mode,'free');self.assertEqual(result.revision,2)

    def test_removing_pro_scope_explains_affected_users(self):
        self.policy.access_mode='pro_or_diamond';self.policy.pro_entitlement_key='member';self.policy.save()
        self.offer.refresh_from_db()
        blocker=next(b for b in publication_checks(self.offer,self.body()) if b['code']=='MIGRATION_REQUIRED')
        self.assertIn('Pro 会员',blocker['message'])
        self.assertIn('请保留原有',blocker['message'])


class OperationInvestigationTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        from datetime import timedelta
        from .models import BillingIdentity,WalletGate,RedemptionQuote,RedemptionOrder,WalletOperation,ContentOwnership
        self.user=User.objects.create_superuser('operator','operator@example.test','test')
        self.identity=BillingIdentity.objects.create(account=self.user,rc_project_id='test',wallet_domain='sandbox')
        WalletGate.objects.create(identity=self.identity)
        offer=ContentOffer.objects.create(target_kind='template',target_id=uuid.uuid4(),title='旅行手帐',state='active')
        policy=ContentPolicyRevision.objects.create(offer=offer,revision=1,access_mode='diamond_only',diamond_price=30,currency_code='DIAMOND')
        quote=RedemptionQuote.objects.create(identity=self.identity,offer=offer,policy_revision=policy,quoted_units=30,expires_at=timezone.now()+timedelta(minutes=10))
        order=RedemptionOrder.objects.create(identity=self.identity,offer=offer,quote=quote,client_request_key=uuid.uuid4(),request_hash='hash',amount=30,status='fulfilled')
        self.operation=WalletOperation.objects.create(identity=self.identity,order=order,kind='debit',delta=-30,state='succeeded',reference='test',request_body_hash='test')
        ContentOwnership.objects.create(identity=self.identity,target_kind='template',target_id=offer.target_id,source_order=order,grant_line='main')
    def test_environment_filter_and_context(self):
        from .operations_admin import list_operations,operation_json
        self.assertEqual(list_operations({'environment':'production'})['total'],0)
        r=list_operations({'environment':'sandbox','q':'旅行'})
        self.assertEqual(r['total'],1);self.assertEqual(r['items'][0]['name'],'operator')
        detail=operation_json(self.operation,detail=True)
        self.assertTrue(detail['can_compensate']);self.assertEqual(detail['revoked_grants'][0]['title'],'旅行手帐')
    def test_pending_compensation_and_unknown_debit_cannot_be_compensated_again(self):
        from .models import WalletOperation
        from .operations_admin import operation_json
        self.operation.state='unknown';self.operation.save()
        self.assertFalse(operation_json(self.operation)['can_compensate'])
        self.operation.state='succeeded';self.operation.save()
        WalletOperation.objects.create(identity=self.identity,order=self.operation.order,kind='compensation',delta=30,state='prepared',reference='refund',request_body_hash='test')
        result=operation_json(self.operation)
        self.assertFalse(result['can_compensate']);self.assertEqual(result['compensation']['state'],'prepared')
