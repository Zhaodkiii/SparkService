import uuid
from unittest.mock import patch
from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory,force_authenticate
from .batch_pricing import BatchPricing
from .models import ContentOffer,ContentPolicyRevision,ContentPolicyDraft
from .pricing import save_draft
from diary_presets.models import Series,Template,Version

@override_settings(DIAMOND_REDEMPTION_ENABLED=True,MEMBERSHIP_SALES_ENABLED=True,BILLING_TEST_POLICY_CHANGES_ENABLED=False)
class BatchDraftTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('batch-admin','batch@example.test','test')
        series=Series.objects.create(slug='batch',title='批量测试')
        self.targets=[]
        for title in ['海边','山野']:
            t=Template.objects.create(series=series,title=title)
            t.current=Version.objects.create(template=t,number=1,snapshot={});t.save();self.targets.append(t)
        self.offer=ContentOffer.objects.create(target_kind='template',target_id=self.targets[0].pk,title='海边',state='active')
        self.policy=ContentPolicyRevision.objects.create(offer=self.offer,revision=1,access_mode='pro_only',pro_entitlement_key='member',terms_version='original-v3')
        self.offer.current_policy_revision=self.policy;self.offer.save()
        self.body=dict(items=[dict(target_kind='template',target_id=str(t.pk)) for t in self.targets],access_mode='free',diamond_price=None,change_reason='批量开放主题',overwrite_drafts=False)
    def call(self,action,body=None):
        r=APIRequestFactory().post('/',body or self.body,format='json');force_authenticate(r,user=self.user)
        return BatchPricing.as_view()(r,action=action)
    def test_preview_is_read_only_and_save_preserves_terms(self):
        p=self.call('preview');self.assertEqual(p.status_code,200);self.assertEqual(p.data['save_count'],2)
        self.assertEqual(ContentOffer.objects.count(),1);self.assertFalse(ContentPolicyDraft.objects.exists())
        result=self.call('save',{**self.body,'expected_preview_hash':p.data['preview_hash']})
        self.assertEqual(result.status_code,200);self.assertEqual(result.data['saved_count'],2)
        self.assertEqual(ContentPolicyDraft.objects.get(offer=self.offer).body['terms_version'],'original-v3')
        self.offer.refresh_from_db();self.assertEqual(self.offer.current_policy_revision.access_mode,'pro_only')
        self.assertEqual(ContentPolicyRevision.objects.count(),1)
    def test_default_skips_existing_draft_and_overwrite_uses_its_terms(self):
        old=dict(expected_revision=1,access_mode='pro_only',diamond_price=None,currency_code=None,pro_entitlement_key='member',bundled_grants=[],terms_version='draft-v4',change_reason='他人草稿')
        save_draft(self.offer.pk,old,self.user)
        p=self.call('preview');self.assertEqual(p.data['skipped_count'],1)
        self.call('save',{**self.body,'expected_preview_hash':p.data['preview_hash']})
        self.assertEqual(ContentPolicyDraft.objects.get(offer=self.offer).body['change_reason'],'他人草稿')
        body={**self.body,'overwrite_drafts':True};p=self.call('preview',body)
        self.assertEqual(p.data['save_count'],2)
        self.call('save',{**body,'expected_preview_hash':p.data['preview_hash']})
        self.assertEqual(ContentPolicyDraft.objects.get(offer=self.offer).body['terms_version'],'draft-v4')
    def test_concurrent_change_rejects_entire_batch(self):
        p=self.call('preview')
        self.policy.terms_version='changed';self.policy.save()
        response=self.call('save',{**self.body,'expected_preview_hash':p.data['preview_hash']})
        self.assertEqual(response.status_code,409);self.assertEqual(ContentOffer.objects.count(),1)
        self.assertFalse(ContentPolicyDraft.objects.exists())
    def test_mid_save_failure_rolls_back_all_drafts_and_new_offers(self):
        p=self.call('preview')
        from .batch_pricing import save_draft as real_save
        from .identity import BillingError
        count=0
        def fail_second(*args,**kwargs):
            nonlocal count
            count+=1
            if count==2:raise BillingError('TEST','模拟保存冲突')
            return real_save(*args,**kwargs)
        with patch('billing.batch_pricing.save_draft',side_effect=fail_second):
            response=self.call('save',{**self.body,'expected_preview_hash':p.data['preview_hash']})
        self.assertEqual(response.status_code,409);self.assertFalse(ContentPolicyDraft.objects.exists())
        self.assertEqual(ContentOffer.objects.count(),1)
    def test_private_content_duplicate_and_oversize_rejected(self):
        self.assertEqual(self.call('preview',{**self.body,'items':[self.body['items'][0]]*2}).status_code,400)
        self.assertEqual(self.call('preview',{**self.body,'items':[dict(target_kind='font',target_id=str(uuid.uuid4())) for _ in range(101)]}).status_code,400)
        t=self.targets[1];t.audience='private';t.owner=self.user;t.customization_id=uuid.uuid4();t.save()
        self.assertEqual(self.call('preview').status_code,404)
        self.assertFalse(ContentPolicyDraft.objects.exists())
    def test_preview_reports_restricted_publication_without_publishing(self):
        body={**self.body,'access_mode':'diamond_only','diamond_price':30}
        p=self.call('preview',body)
        row=next(r for r in p.data['items'] if r['title']=='海边')
        self.assertIn('MIGRATION_REQUIRED',[b['code'] for b in row['blockers']])
        self.assertEqual(self.call('save',{**body,'expected_preview_hash':p.data['preview_hash']}).status_code,200)
        self.assertEqual(ContentPolicyRevision.objects.count(),1)
    def test_read_only_cannot_preview_or_save(self):
        self.user.is_superuser=False;self.user.save()
        with patch('common.permissions.has_permission_code',return_value=False):
            self.assertEqual(self.call('preview').status_code,403)
            self.assertEqual(self.call('save').status_code,403)

    def test_publish_entire_batch_without_separate_draft_step(self):
        preview=self.call('preview')
        result=self.call('publish',{**self.body,'expected_preview_hash':preview.data['preview_hash']})
        self.assertEqual(result.status_code,200);self.assertEqual(result.data['published_count'],2)
        self.assertEqual(ContentPolicyRevision.objects.count(),3)
        self.assertFalse(ContentPolicyDraft.objects.exists())
        self.offer.refresh_from_db();self.assertEqual(self.offer.current_policy_revision.access_mode,'free')

    def test_publish_blocks_all_if_any_item_is_blocked(self):
        body={**self.body,'access_mode':'diamond_only','diamond_price':30}
        preview=self.call('preview',body)
        result=self.call('publish',{**body,'expected_preview_hash':preview.data['preview_hash']})
        self.assertEqual(result.status_code,409);self.assertEqual(ContentPolicyRevision.objects.count(),1)
        self.assertEqual(ContentOffer.objects.count(),1);self.assertFalse(ContentPolicyDraft.objects.exists())

    def test_publish_rejects_skipped_existing_drafts(self):
        old=dict(expected_revision=1,access_mode='pro_only',diamond_price=None,currency_code=None,pro_entitlement_key='member',bundled_grants=[],terms_version='draft-v4',change_reason='已有草稿')
        save_draft(self.offer.pk,old,self.user)
        preview=self.call('preview')
        result=self.call('publish',{**self.body,'expected_preview_hash':preview.data['preview_hash']})
        self.assertEqual(result.status_code,409);self.assertEqual(ContentPolicyRevision.objects.count(),1)
        self.assertEqual(ContentPolicyDraft.objects.get(offer=self.offer).body['change_reason'],'已有草稿')

    def test_publish_rolls_back_when_later_publish_fails(self):
        preview=self.call('preview')
        from .batch_pricing import publish as real_publish
        from .identity import BillingError
        count=0
        def fail_second(*args,**kwargs):
            nonlocal count
            count+=1
            if count==2:raise BillingError('TEST','模拟发布冲突')
            return real_publish(*args,**kwargs)
        with patch('billing.batch_pricing.publish',side_effect=fail_second):
            result=self.call('publish',{**self.body,'expected_preview_hash':preview.data['preview_hash']})
        self.assertEqual(result.status_code,409);self.assertEqual(ContentPolicyRevision.objects.count(),1)
        self.assertEqual(ContentOffer.objects.count(),1);self.assertFalse(ContentPolicyDraft.objects.exists())
        self.offer.refresh_from_db();self.assertEqual(self.offer.current_policy_revision.access_mode,'pro_only')

    def test_publish_requires_both_permissions(self):
        preview=self.call('preview');self.user.is_superuser=False;self.user.save()
        with patch('common.permissions.has_permission_code',side_effect=lambda uid,p:p=='billing.publish_pricing'), patch('backoffice.rbac.has_permission_code',return_value=False):
            result=self.call('publish',{**self.body,'expected_preview_hash':preview.data['preview_hash']})
        self.assertEqual(result.status_code,403);self.assertEqual(ContentPolicyRevision.objects.count(),1)
