from datetime import timedelta
import uuid
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from accounts.models import SocialIdentity
from print_orders.models import Product,PrintCampaign,PrintCoupon
from ai_production.models import ProductionResetCard,ProductionPolicy,ProductionWindow,ProductionQuotaReset
from ai_production.reset_cards import use_card
from billing.models import BillingIdentity,MembershipSnapshot
from .models import *
from .invitations import join,register,process_identity,issue,validate_campaign

class InvitationFlowTests(TestCase):
    def setUp(self):
        self.owner=get_user_model().objects.create_user('inviter')
        SocialIdentity.objects.create(user=self.owner,provider='email',provider_uid='owner@example.com')
        now=timezone.now()
        product=Product.objects.create(title='标准册',active=True,proof_approved=True,base_fen=1000,page_fen=100)
        plan=PrintCampaign.objects.create(title='邀请印制',source='invitation',product=product,starts_at=now-timedelta(days=1),ends_at=now+timedelta(days=30),cap_fen=10000,quota=100)
        self.c=InvitationCampaign.objects.create(title='邀请',active=True,starts_at=now-timedelta(days=1),ends_at=now+timedelta(days=30),download_url='https://apps.apple.com/cn/app/id123456',print_campaign=plan,rules='标准20页，不含运费',cards_per_invite=1)
        self.link=join(self.owner,self.c)
    def convert(self,n):
        email=f'friend{n}@example.com';reg=register(self.link,'email',email)
        user=get_user_model().objects.create_user(f'friend{n}')
        identity=SocialIdentity.objects.create(user=user,provider='email',provider_uid=email)
        event=InvitationIdentityEvent.objects.create(identity=identity)
        process_identity(event.pk)
        return user,event,reg
    def test_registration_does_not_count_and_is_idempotent(self):
        a=register(self.link,'email','new@example.com');b=register(self.link,'email','NEW@example.com')
        self.assertEqual(a.pk,b.pk);self.assertEqual(InvitationConversion.objects.count(),0)
    def test_duplicate_events_count_and_award_once(self):
        u,e,_=self.convert(1);process_identity(e.pk)
        other=InvitationIdentityEvent.objects.create(identity=e.identity);process_identity(other.pk)
        self.assertEqual(InvitationConversion.objects.count(),1)
        r=InvitationReward.objects.get();issue(r.pk);issue(r.pk)
        self.assertEqual(ProductionResetCard.objects.count(),1)
    def test_two_milestones_issue_separate_coupons(self):
        for n in range(10):self.convert(n)
        for r in InvitationReward.objects.all():issue(r.pk);issue(r.pk)
        self.assertEqual(list(PrintCoupon.objects.order_by('percent').values_list('percent',flat=True)),[50,100])
        self.assertEqual(ProductionResetCard.objects.count(),10)
    def test_conflicting_registration_not_auto_attributed(self):
        other=get_user_model().objects.create_user('other')
        SocialIdentity.objects.create(user=other,provider='email',provider_uid='other@example.com')
        otherlink=join(other,self.c)
        register(otherlink,'email','friend1@example.com')
        self.convert(1)
        self.assertFalse(InvitationConversion.objects.exists())
    def test_existing_identity_cannot_register(self):
        with self.assertRaises(ValidationError):register(self.link,'email','owner@example.com')
    def test_closed_campaign_and_capacity(self):
        self.c.participant_limit=1;self.c.save()
        other=get_user_model().objects.create_user('other');SocialIdentity.objects.create(user=other,provider='email',provider_uid='other@example.com')
        with self.assertRaises(ValidationError):join(other,self.c)
        self.c.active=False;self.c.save();self.link.refresh_from_db()
        with self.assertRaises(ValidationError):register(self.link,'email','new@example.com')
    def test_download_and_cost_validation(self):
        self.c.download_url='https://evil.example/id123'
        with self.assertRaises(ValidationError):validate_campaign(self.c)
    def test_admin_rejects_ordinary_user(self):
        client=APIClient();client.force_authenticate(self.owner)
        self.assertEqual(client.get('/api/admin/v1/experience/invitations/').status_code,403)
    def test_public_register_no_auth_and_no_sensitive_persistence(self):
        response=APIClient().post(f'/api/public/v1/invitations/{self.link.pk}/',{'contact_kind':'email','contact':'new@example.com'},format='json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['data']['status'],'awaiting_app')
        self.assertNotIn('new@example.com',str(list(InvitationRegistration.objects.values())))

class ResetCardTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('card-user')
        self.policy=ProductionPolicy.objects.create(free_weekly_limit_points=10,short_limit_points=30,weekly_limit_points=100)
        now=timezone.now()
        self.week=ProductionWindow.objects.create(account=self.user,kind='weekly',starts_at=now-timedelta(hours=1),ends_at=now+timedelta(days=6),policy=self.policy,limit_points=10,used_points=5)
        self.short=ProductionWindow.objects.create(account=self.user,kind='short',starts_at=now-timedelta(hours=1),ends_at=now+timedelta(hours=4),policy=self.policy,limit_points=30,used_points=2)
        self.card=ProductionResetCard.objects.create(owner=self.user,grant_key='test',expires_at=now+timedelta(days=1))
    def test_free_only_weekly_and_idempotent(self):
        key=uuid.uuid4();use_card(self.user,self.card.pk,key,'free',None);use_card(self.user,self.card.pk,key,'free',None)
        self.week.refresh_from_db();self.short.refresh_from_db()
        self.assertLessEqual(self.week.ends_at,timezone.now());self.assertGreater(self.short.ends_at,timezone.now())
        self.assertEqual(self.week.used_points,5)
        self.assertEqual(ProductionQuotaReset.objects.count(),1)
    def test_pro_resets_both_using_verified_sandbox_identity(self):
        i=BillingIdentity.objects.create(account=self.user,rc_project_id='test',wallet_domain='sandbox')
        MembershipSnapshot.objects.create(identity=i,verified_at=timezone.now(),active_until=timezone.now()+timedelta(days=1),needs_sync=False)
        use_card(self.user,self.card.pk,uuid.uuid4(),'pro',i)
        self.short.refresh_from_db();self.assertLessEqual(self.short.ends_at,timezone.now())
    def test_expired_card_not_consumed(self):
        self.card.expires_at=timezone.now()-timedelta(seconds=1);self.card.save()
        with self.assertRaises(ValidationError):use_card(self.user,self.card.pk,uuid.uuid4(),'free',None)
        self.card.refresh_from_db();self.assertIsNone(self.card.used_reset_id)
    def test_second_card_cannot_reset_already_full(self):
        use_card(self.user,self.card.pk,uuid.uuid4(),'free',None)
        second=ProductionResetCard.objects.create(owner=self.user,grant_key='second',expires_at=timezone.now()+timedelta(days=1))
        with self.assertRaises(ValidationError):use_card(self.user,second.pk,uuid.uuid4(),'free',None)
        second.refresh_from_db();self.assertIsNone(second.used_reset_id)

    def test_changed_plan_and_other_owner_rejected_without_consuming(self):
        with self.assertRaises(ValidationError):use_card(self.user,self.card.pk,uuid.uuid4(),'pro',None)
        self.card.refresh_from_db();self.assertIsNone(self.card.used_reset_id)
        from django.http import Http404
        other=get_user_model().objects.create_user('wrong-owner')
        with self.assertRaises(Http404):use_card(other,self.card.pk,uuid.uuid4(),'free',None)

    def test_pending_call_blocks_card_and_keeps_history(self):
        from ai_production.models import ProductionTask,ProductionCall
        task=ProductionTask.objects.create(account=self.user,attempt_key=uuid.uuid4(),input_digest='a'*64)
        ProductionCall.objects.create(id=uuid.uuid4(),task=task,weekly_window=self.week,policy=self.policy,rate={},budget=1,usage_due_at=timezone.now()+timedelta(minutes=1))
        with self.assertRaises(ValidationError):use_card(self.user,self.card.pk,uuid.uuid4(),'free',None)
        self.card.refresh_from_db();self.assertIsNone(self.card.used_reset_id)
