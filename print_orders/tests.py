import json
import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from accounts.models import SocialIdentity
from .models import Product, Order, Shipment, Production, FileCleanup
from .domain import Conflict, Unavailable
from .operations import CHECKLISTS


class PrintTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='print-reader',password='test')
        SocialIdentity.objects.create(user=self.user,provider='email',provider_uid='print@example.test')
        self.other=get_user_model().objects.create_user(username='other',password='test')
        self.admin=get_user_model().objects.create_superuser(username='printer',password='test',email='p@example.test')
        self.client=APIClient(); self.client.force_authenticate(self.user)
        self.product=Product.objects.create(title='A5',active=True,proof_approved=True,paper='测试纸',binding='测试装订',base_fen=1000,page_fen=10,regions=['上海'],terms='测试')
        self.body=dict(key=str(uuid.uuid4()),product_id=str(self.product.id),product_revision=1,title='旅行',quantity=1,page_count=2,
            address=dict(name='测试用户',phone='13800000000',region='上海',detail='测试地址'),quote_total_fen=1020,confirmed=True,
            snapshot=dict(book_id=str(uuid.uuid4()),catalog_revision=str(uuid.uuid4()),exporter_version='print-v1',
                pages=[dict(page_id=str(uuid.uuid4()),revision_id=str(uuid.uuid4()),role=role) for role in ['shell','interior']]),
            files=[dict(role=role,sha256='a'*64,size=10,page_count=1 if role=='cover' else 2) for role in ['interior','cover']])
    def create(self):
        r=self.client.post('/api/v1/print/orders/',self.body,format='json')
        self.assertEqual(r.status_code,201,r.data)
        return Order.objects.get(pk=r.data['id'])
    def action(self,o,action,**kwargs):
        return self.client.post(f'/api/v1/print/orders/{o.id}/actions/',dict(key=str(uuid.uuid4()),revision=o.revision,action=action,**kwargs),format='json')
    def test_creation_idempotent_and_payload_bound(self):
        self.create()
        self.assertEqual(self.client.post('/api/v1/print/orders/',self.body,format='json').status_code,200)
        self.body['title']='changed'
        self.assertEqual(self.client.post('/api/v1/print/orders/',self.body,format='json').status_code,409)
        self.assertEqual(Order.objects.count(),1)
    def test_paid_annual_event_is_idempotent_and_refund_expires_coupon(self):
        from datetime import timedelta
        from django.utils import timezone
        from billing.models import BillingIdentity, CurrencyEvent
        from billing.tasks import process_event
        from .models import PrintCampaign, PrintCoupon
        now=timezone.now()
        identity=BillingIdentity.objects.create(account=self.user,rc_project_id='coupon-test',wallet_domain='production')
        PrintCampaign.objects.create(title='年费开通礼',source='annual',active=True,starts_at=now-timedelta(days=1),
            ends_at=now+timedelta(days=1),product=self.product,annual_product_id='annual-test',cap_fen=2000,quota=1)
        data=dict(app_user_id=str(identity.rc_app_user_id),type='INITIAL_PURCHASE',environment='PRODUCTION',
            entitlement_ids=['member'],price_in_purchased_currency=99,currency='CNY',store='APP_STORE',
            product_id='annual-test',transaction_id='tx-1',app_id='app',purchased_at_ms=int(now.timestamp()*1000),
            event_timestamp_ms=int(now.timestamp()*1000))
        for i in range(2):
            event=CurrencyEvent.objects.create(event_id=f'purchase-{i}',payload=data)
            process_event(event.pk)
        coupon=PrintCoupon.objects.get(owner=self.user)
        self.assertGreater(coupon.expires_at,now)
        event=CurrencyEvent.objects.create(event_id='refund-annual',payload={**data,'type':'CANCELLATION','cancel_reason':'CUSTOMER_SUPPORT'})
        process_event(event.pk)
        coupon.refresh_from_db()
        self.assertLessEqual(coupon.expires_at,timezone.now())

    def test_coupon_preview_binds_terms_and_retry_returns_original(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import PrintCoupon
        self.client.force_authenticate(self.admin)
        url = '/api/admin/v1/print/coupons/'
        body = dict(owner=self.user.pk, product=str(self.product.pk), percent=50, included_pages=2,
                    cap_fen=500, expires_at=(timezone.now()+timedelta(days=1)).isoformat(), ticket='case-1')
        self.assertEqual(self.client.post(url, body, format='json').status_code, 409)
        preview = self.client.post(url, dict(body, preview=True), format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(PrintCoupon.objects.count(), 0)
        body['confirmation'] = preview.data['confirmation']
        self.assertEqual(self.client.post(url, dict(body, cap_fen=300), format='json').status_code, 409)
        first = self.client.post(url, body, format='json')
        retry = self.client.post(url, body, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(retry.data, dict(id=first.data['id'], created=False))

    def ai_faces(self, count):
        from datetime import timedelta
        from django.utils import timezone
        from ai_production.models import ProductionPolicy, ProductionWindow, ProductionTask, ProductionLedger

        now = timezone.now()
        policy = ProductionPolicy.objects.create(name='测试', short_limit=100, weekly_limit=100)
        windows = [ProductionWindow.objects.create(account=self.user, kind=kind, starts_at=now,
                   ends_at=now+timedelta(days=1), policy=policy, limit=100) for kind in ('short', 'weekly')]
        faces = []
        for _ in range(count):
            page = str(uuid.uuid4())
            task = ProductionTask.objects.create(account=self.user, attempt_key=uuid.uuid4(), state='completed',
                    input_digest='a'*64, short_window=windows[0], weekly_window=windows[1], expires_at=now,
                    result={'page_id': page, 'faces': ['left']})
            ProductionLedger.objects.create(task=task, reservation_id=task.reservation_id, event='settle',
                                           short_window=windows[0], weekly_window=windows[1])
            faces.append(dict(task=str(task.pk), page=page, revision=str(uuid.uuid4()), face='left', first_saved=now.isoformat()))
        return faces

    def test_campaign_console_and_wallet(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import PrintEnrollment
        url='/api/admin/v1/print/campaigns/'
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_authenticate(self.admin)
        now=timezone.now()
        body=dict(action='create', title='测试装订活动', source='pages', active=False, product=str(self.product.pk),
                  starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1), included_pages=40,
                  cap_fen=2000, valid_days=30, quota=1)
        response=self.client.post(url,body,format='json')
        self.assertEqual(response.status_code,200,response.data)
        created = response.data
        preview = self.client.post(url, dict(body, action='preview'), format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual([s['percent'] for s in preview.data['samples']], [50, 100])
        updated = self.client.post(url, dict(body, action='update', id=created['id'],
                                             version=created['version'], title='修订活动'), format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(self.client.post(url, dict(action='publish', id=created['id'],
                                                    version=created['version']), format='json').status_code, 409)
        published = self.client.post(url, dict(action='publish', id=created['id'],
                                               version=updated.data['version']), format='json')
        self.assertEqual(published.status_code, 200, published.data)
        self.client.force_authenticate(self.user)
        plan=self.client.get('/api/v1/print/campaign/').data
        response=self.client.post(f"/api/v1/print/campaign/{plan['id']}/join/",
                                  dict(book_id=str(uuid.uuid4()),pages=400,faces=self.ai_faces(40)),format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['enrollment']['reported_pages'], 40)
        self.assertFalse(response.data['enrollment']['coupon_available'])
        self.client.force_authenticate(self.admin)
        for tier in (20,40,40):
            response=self.client.post(url,dict(action='approve',id=PrintEnrollment.objects.get().pk,tier=tier),format='json')
            self.assertEqual(response.status_code,200,response.data)
        self.client.force_authenticate(self.user)
        placement = self.client.get('/api/v1/print/campaign/', {'book': str(PrintEnrollment.objects.get().book_id)})
        self.assertEqual(placement.data['enrollment']['approved_pages'], 40)
        self.assertEqual(placement.data['enrollment']['coupon_percent'], 100)
        self.assertTrue(placement.data['enrollment']['coupon_available'])
        wallet=self.client.get('/api/v1/print/coupons/mine/').data
        self.assertEqual([c['name'] for c in wallet],['标准装订免费券'])

    def test_ai_activity_evidence_binds_owner_page_face_and_window(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import PrintCampaign, PrintEnrollment

        now = timezone.now()
        plan = PrintCampaign.objects.create(title='AI内页', source='pages', active=True, product=self.product,
            starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1), cap_fen=100, quota=3)
        url = f'/api/v1/print/campaign/{plan.pk}/join/'
        data = dict(book_id=str(uuid.uuid4()), pages=999)
        self.assertEqual(self.client.post(url, data, format='json').status_code, 400)
        face, = self.ai_faces(1)
        data['faces'] = [face, face, dict(face, page=str(uuid.uuid4())), dict(face, face='right')]
        for _ in range(2):
            self.assertEqual(self.client.post(url, data, format='json').data['enrollment']['reported_pages'], 1)
        entry = PrintEnrollment.objects.get()
        self.assertEqual(len(entry.page_evidence), 4)
        self.client.force_authenticate(self.other)
        response = self.client.post('/api/v1/print/campaign/', {'faces':[face]}, format='json')
        self.assertTrue(response.data['assessed_faces'][0]['reason'])
        self.client.force_authenticate(self.user)
        plan.starts_at = timezone.now()
        plan.save()
        self.assertEqual(self.client.post(url, data, format='json').data['enrollment']['reported_pages'], 0)

    def test_book_experience_recovers_history_and_review_results(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import PrintCampaign, PrintEnrollment, PrintCoupon
        from .campaigns import book_experience

        now = timezone.now()
        self.assertEqual(self.client.get('/api/v1/print/campaign/').data['experience']['status'], 'no_activity')
        plan = PrintCampaign.objects.create(title='定制页状态测试', source='pages', active=True, product=self.product,
            starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1), cap_fen=400, quota=5)
        self.assertEqual(book_experience(plan, None)['action'], 'join')
        entry = PrintEnrollment.objects.create(plan=plan, owner=self.user, book_id=self.body['snapshot']['book_id'],
                                               reported_pages=2)
        self.assertEqual(book_experience(plan, entry)['progress'], 0.05)
        self.assertEqual(book_experience(plan, entry, 20)['status'], 'submit_half')
        entry.reported_pages = 20
        self.assertEqual(book_experience(plan, entry)['status'], 'half_pending')
        entry.reported_pages = 42
        self.assertEqual(book_experience(plan, entry)['heading'], '40 页档核验中')
        coupon = PrintCoupon.objects.create(owner=self.user, product=self.product, name='测试券', percent=50,
            included_pages=40, cap_fen=400, expires_at=now+timedelta(days=30), grant_key='context')
        entry.coupon = coupon
        entry.approved_pages = 20
        entry.reported_pages = 20
        self.assertEqual(book_experience(plan, entry)['action_title'], '继续做到 40 页')
        self.assertEqual(book_experience(plan, entry, 40)['status'], 'submit_full')
        self.assertEqual(book_experience(plan, entry)['rewards'][0]['title'], '装订抵扣 ¥4.00')
        entry.approved_pages = 40
        coupon.percent = 100
        coupon.save()
        self.assertEqual(book_experience(plan, entry)['action'], 'checkout')
        entry.save()
        plan.ends_at = now-timedelta(hours=1)
        plan.active = False
        plan.save()
        context = self.client.get('/api/v1/print/campaign/', {'book': entry.book_id}).data
        self.assertTrue(context['experience']['historical'])
        self.assertEqual(context['experience']['coupon_id'], str(coupon.pk))
        self.assertEqual(context['experience']['status'], 'full_ready')

        order = self.create()
        coupon.order = order
        coupon.percent = 50
        coupon.save()
        entry.coupon = coupon
        self.assertEqual(book_experience(plan, entry)['status'], 'upgrade_waiting')
        order.transaction_id = 'verified-payment'
        order.save()
        self.assertEqual(book_experience(plan, entry)['status'], 'used')

    def test_review_feedback_resubmits_same_count_and_preserves_reason(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import PrintCampaign, PrintEnrollment

        now = timezone.now()
        plan = PrintCampaign.objects.create(title='审核反馈', ai_pages_only=False, source='pages', active=True, product=self.product,
            starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1), cap_fen=2000, quota=1)
        book = self.body['snapshot']['book_id']
        entry = PrintEnrollment.objects.create(plan=plan, owner=self.user, book_id=book, reported_pages=40)
        admin_url = '/api/admin/v1/print/campaigns/'
        page_id = self.body['snapshot']['pages'][1]['page_id']
        self.client.force_authenticate(self.admin)
        result = self.client.post(admin_url, dict(action='return', id=entry.pk, attempt=1, reason='第 2 页需补充内容',
                                                  page_ids=[page_id]), format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.client.get(admin_url).data['total_pending'], 0)
        self.assertEqual(self.client.post(admin_url, dict(action='approve', id=entry.pk, attempt=1,tier=40),
                                         format='json').status_code, 409)
        self.client.force_authenticate(self.user)
        experience = self.client.get('/api/v1/print/campaign/', {'book': book}).data['experience']
        self.assertEqual(experience['status'], 'returned')
        self.assertEqual(experience['review_page_ids'], [page_id])
        self.assertTrue(experience['can_resubmit'])
        submitted = self.client.post(f'/api/v1/print/campaign/{plan.pk}/join/', dict(book_id=book,pages=40,attempt=1), format='json')
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(admin_url).data['total_pending'], 1)
        result = self.client.post(admin_url, dict(action='approve', id=entry.pk,attempt=1,tier=40), format='json')
        self.assertEqual(result.status_code, 200, result.data)
        entry.refresh_from_db()
        self.assertEqual(entry.participation_history[1]['reason'], '第 2 页需补充内容')

    def test_unrestricted_campaign_coupon_quotes_multiple_products_and_locks_once(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import PrintEnrollment

        now = timezone.now()
        second = Product.objects.create(title='B5', active=True, proof_approved=True, paper='纸', binding='装订',
                                        base_fen=2000, shipping_fen=300, regions=['上海'])
        admin_url = '/api/admin/v1/print/campaigns/'
        body = dict(title='不限规格活动', source='pages', product=None, active=False,
                    starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1),
                    included_pages=40, cap_fen=5000, valid_days=30, quota=5)
        self.client.force_authenticate(self.admin)
        preview = self.client.post(admin_url, dict(body, action='preview'), format='json')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual([q['product'] for q in preview.data['quotes']], ['A5', 'B5'])
        created = self.client.post(admin_url, dict(body, action='create'), format='json').data
        publish = self.client.post(admin_url, dict(action='publish', id=created['id'], version=created['version']), format='json')
        self.assertEqual(publish.status_code, 200, publish.data)
        self.client.force_authenticate(self.user)
        book_id = self.body['snapshot']['book_id']
        placement = self.client.get('/api/v1/print/campaign/', {'book': book_id}).data
        self.assertTrue(placement['unrestricted'])
        joined = self.client.post(f"/api/v1/print/campaign/{created['id']}/join/", dict(book_id=book_id, pages=40, faces=self.ai_faces(40)), format='json')
        self.assertEqual(joined.status_code, 200, joined.data)
        self.client.force_authenticate(self.admin)
        entry = PrintEnrollment.objects.get()
        approved = self.client.post(admin_url, dict(action='approve', id=entry.pk, tier=40), format='json')
        self.assertEqual(approved.status_code, 200, approved.data)
        entry.refresh_from_db()
        self.assertIsNone(entry.coupon.product_id)
        self.client.force_authenticate(self.user)
        wallet = self.client.get('/api/v1/print/coupons/mine/').data
        self.assertEqual(wallet[0]['product'], '不限印制规格')
        coupon_id = str(entry.coupon_id)
        for product, payable in ((self.product, 0), (second, 300)):
            result = self.client.post('/api/v1/print/quotes/', dict(product_id=str(product.pk), page_count=2,
                quantity=1, region='上海', coupon_selection=coupon_id), format='json')
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual(result.data['total_fen'], payable)
        self.body.update(product_id=str(second.pk), coupon_id=coupon_id, quote_total_fen=300)
        self.create()
        self.body.update(key=str(uuid.uuid4()), product_id=str(self.product.pk), quote_total_fen=0)
        self.assertEqual(self.client.post('/api/v1/print/orders/', self.body, format='json').status_code, 409)

    def test_campaign_withdrawal_releases_only_unrewarded_places(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import PrintCampaign, PrintEnrollment

        now = timezone.now()
        plan = PrintCampaign.objects.create(title='制作达标', ai_pages_only=False, source='pages', active=True,
            product=self.product, starts_at=now-timedelta(days=1), ends_at=now+timedelta(days=1),
            cap_fen=2000, quota=1)
        base = f'/api/v1/print/campaign/{plan.pk}/'
        admin_url = '/api/admin/v1/print/campaigns/'
        book_id = str(uuid.uuid4())
        body = dict(book_id=book_id, pages=40)
        self.assertEqual(self.client.post(base+'join/', body, format='json').status_code, 200)
        entry = PrintEnrollment.objects.get()
        withdrawal = dict(book_id=book_id, attempt=1)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(base+'withdraw/', withdrawal, format='json').status_code, 404)
        self.client.force_authenticate(self.user)
        first = self.client.post(base+'withdraw/', withdrawal, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(self.client.post(base+'withdraw/', withdrawal, format='json').data, first.data)
        self.assertEqual(self.client.post(base+'join/', body, format='json').status_code, 409)

        self.client.force_authenticate(self.admin)
        approve = dict(action='approve', id=entry.pk, tier=40, attempt=1)
        self.assertEqual(self.client.post(admin_url, approve, format='json').status_code, 409)
        console = self.client.get(admin_url).data
        self.assertEqual(console['plans'][0]['remaining'], 1)
        self.assertEqual(console['total_pending'], 0)
        participants = self.client.get(admin_url, {'participants': plan.pk, 'status': 'withdrawn', 'q': book_id}).data
        self.assertEqual(participants['total'], 1)
        self.assertEqual([e['event'] for e in participants['participants'][0]['history']],
                         ['joined', 'progress', 'withdrawn'])

        self.client.force_authenticate(self.user)
        rejoined = self.client.post(base+'join/', dict(body, rejoin=True, attempt=1), format='json')
        self.assertEqual(rejoined.status_code, 200, rejoined.data)
        self.assertEqual(rejoined.data['enrollment']['attempt'], 2)
        self.assertEqual(self.client.post(base+'withdraw/', withdrawal, format='json').status_code, 409)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(admin_url, approve, format='json').status_code, 409)
        self.assertEqual(self.client.post(admin_url, dict(approve, attempt=2), format='json').status_code, 200)

        self.client.force_authenticate(self.user)
        result = self.client.post(base+'withdraw/', dict(withdrawal, attempt=2), format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertTrue(result.data['enrollment']['coupon_available'])
        self.assertEqual(self.client.post(base+'join/', dict(body, rejoin=True, attempt=2), format='json').status_code, 409)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(admin_url).data['plans'][0]['remaining'], 0)

    def test_coupon_limits_discount_to_one_copy_and_releases_on_cancel(self):
        from datetime import timedelta
        from django.utils import timezone
        from .models import PrintCoupon
        coupon = PrintCoupon.objects.create(owner=self.user, product=self.product, percent=100,
            name='标准装订券', included_pages=2, cap_fen=5000, grant_key='test:1',
            expires_at=timezone.now()+timedelta(days=1))
        self.product.shipping_fen = 500
        self.product.save()
        self.body.update(quantity=2, coupon_id=str(coupon.pk), quote_total_fen=1520)
        order = self.create()
        coupon.refresh_from_db()
        self.assertEqual(coupon.order_id, order.pk)
        self.body['key'] = str(uuid.uuid4())
        self.assertEqual(self.client.post('/api/v1/print/orders/',self.body,format='json').status_code,409)
        self.assertEqual(self.action(order,'cancel').status_code,200)
        coupon.refresh_from_db()
        self.assertIsNone(coupon.order_id)

    def test_snapshot_survives_product_change(self):
        o=self.create();self.product.title='different';self.product.base_fen=5000;self.product.save()
        o.refresh_from_db();self.assertEqual(o.spec['title'],'A5');self.assertEqual(o.total_fen,1020)
    def test_owner_scoped_detail_and_upload(self):
        o=self.create();self.client.force_authenticate(self.other)
        for tail in ['', 'upload/']:
            method=self.client.post if tail else self.client.get
            self.assertEqual(method(f'/api/v1/print/orders/{o.id}/{tail}').status_code,404)
    def test_client_price_is_not_trusted(self):
        self.body['quote_total_fen']=1
        self.assertEqual(self.client.post('/api/v1/print/orders/',self.body,format='json').status_code,409)
    def test_unapproved_product_hidden_and_unorderable(self):
        self.product.proof_approved=False;self.product.save()
        self.assertEqual(self.client.get('/api/v1/print/products/').data,[])
        self.assertEqual(self.client.post('/api/v1/print/orders/',self.body,format='json').status_code,400)
    def test_duplicate_page_mapping_rejected(self):
        self.body['snapshot']['pages'][1]['page_id']=self.body['snapshot']['pages'][0]['page_id']
        self.assertEqual(self.client.post('/api/v1/print/orders/',self.body,format='json').status_code,400)
    def test_unready_files_cannot_pay(self):
        o=self.create()
        self.assertEqual(self.client.post(f'/api/v1/print/orders/{o.id}/payments/').status_code,409)
    def test_cancel_idempotent_and_stale_rejected(self):
        o=self.create(); d=dict(key=str(uuid.uuid4()),revision=o.revision,action='cancel')
        url=f'/api/v1/print/orders/{o.id}/actions/'
        self.assertEqual(self.client.post(url,d,format='json').status_code,200)
        self.assertEqual(self.client.post(url,d,format='json').status_code,200)
        d['key']=str(uuid.uuid4())
        self.assertEqual(self.client.post(url,d,format='json').status_code,409)
    def test_admin_cannot_start_unpaid_order(self):
        o=self.create();self.client.force_authenticate(self.admin)
        r=self.client.post(f'/api/admin/v1/print/orders/{o.id}/',dict(key=str(uuid.uuid4()),revision=o.revision,action='start'),format='json')
        self.assertEqual(r.status_code,409)
    def test_fulfillment_and_download_does_not_start(self):
        o=self.create();o.file_state='ready';o.payment_state='paid';o.state='awaiting_review';o.save()
        p=o.current_production;p.result={'files':{'archive':{'key':'traveldiary/print/production/test.zip'}}};p.state='ready';p.save()
        self.client.force_authenticate(self.admin)
        with patch('print_orders.storage.download',return_value='https://example.test/a'):
            self.assertEqual(self.client.post(f'/api/admin/v1/print/orders/{o.id}/downloads/').status_code,200)
        o.refresh_from_db();self.assertEqual(o.state,'awaiting_review')
        for action in ['approve','start','finish','ship']:
            r=self.client.post(f'/api/admin/v1/print/orders/{o.id}/',dict(key=str(uuid.uuid4()),revision=o.revision,action=action,checklist=list(CHECKLISTS.get(action, {})),production_id=str(o.current_production_id),address_confirmed=True,carrier='顺丰',tracking_number='SF123456789'),format='json')
            self.assertEqual(r.status_code,200,r.data);o.refresh_from_db()
        self.assertEqual(o.state,'shipped');self.assertEqual(Shipment.objects.count(),1)
    def test_missing_wechat_configuration_fails_closed(self):
        from .wechat import config
        with override_settings(PRINT_WXPAY_APPID=''):
            with self.assertRaises(Unavailable): config()


class WeChatSignatureTests(TestCase):
    def test_signed_notification_decrypts_and_rejects_tampering(self):
        import base64, tempfile, time
        from pathlib import Path
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa, padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from . import wechat
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        secret='1'*32
        payload=dict(out_trade_no='a'*32,trade_state='SUCCESS')
        encrypted=AESGCM(secret.encode()).encrypt(b'123456789012',json.dumps(payload).encode(),b'transaction')
        body=json.dumps({'resource':dict(algorithm='AEAD_AES_256_GCM',nonce='123456789012',associated_data='transaction',ciphertext=base64.b64encode(encrypted).decode())}).encode()
        stamp=str(int(time.time()));nonce='nonce'
        signature=base64.b64encode(key.sign(f'{stamp}\n{nonce}\n'.encode()+body+b'\n',padding.PKCS1v15(),hashes.SHA256())).decode()
        headers={'Wechatpay-Timestamp':stamp,'Wechatpay-Nonce':nonce,'Wechatpay-Serial':'PUB_KEY_ID_1','Wechatpay-Signature':signature}
        with tempfile.TemporaryDirectory() as temp:
            pub=Path(temp)/'public.pem';pub.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
            cfg=dict(PUBLIC_KEY_PATH=str(pub),PUBLIC_KEY_ID='PUB_KEY_ID_1',API_V3_KEY=secret)
            with patch('print_orders.wechat.config',return_value=cfg):
                self.assertEqual(wechat.notification(headers,body),payload)
                with self.assertRaises(ValueError):wechat.notification(headers,body+b' ')
                with self.assertRaises(ValueError):wechat.notification({**headers,'Wechatpay-Serial':'other'},body)
                with self.assertRaises(ValueError):wechat.notification({**headers,'Wechatpay-Timestamp':'1'},body)

    def test_transport_error_never_becomes_success(self):
        import requests
        from . import wechat
        with patch('print_orders.wechat.config',return_value={'MCHID':'m','SERIAL':'s','PUBLIC_KEY_ID':'p'}), patch('print_orders.wechat.sign',return_value='signature'), patch('print_orders.wechat.requests.request',side_effect=requests.Timeout):
            with self.assertRaises(Unavailable):wechat.request('POST','/v3/pay/transactions/app',{})

class FreePrintTests(TestCase):
    create = PrintTests.create
    action = PrintTests.action

    def setUp(self):
        PrintTests.setUp(self)
        self.product.free_printing=True; self.product.save()
        self.body['quote_total_fen']=0

    def test_free_order_enters_review_after_file_check_and_can_ship(self):
        o=self.create()
        self.assertEqual(o.payment_state,'not_required')
        self.assertEqual(o.state,'draft')
        self.assertEqual(o.total_fen,0)
        self.assertEqual(self.client.post(f'/api/v1/print/orders/{o.id}/payments/').status_code,409)
        response=self.client.post(f'/api/v1/print/orders/{o.id}/complete-upload/',dict(production_id=str(o.current_production_id),client_confirmed=True,completed_roles=['cover','interior']),format='json')
        self.assertEqual(response.status_code,200,response.data)
        o.refresh_from_db();self.assertEqual(o.state,'awaiting_review');self.assertFalse(o.payment_started)
        self.client.force_authenticate(self.admin)
        with patch('print_orders.storage.download',return_value='https://example.test/file'):
            self.assertEqual(self.client.post(f'/api/admin/v1/print/orders/{o.id}/downloads/').status_code,200)
        for action in ['approve','start','finish','ship']:
            r=self.client.post(f'/api/admin/v1/print/orders/{o.id}/',dict(key=str(uuid.uuid4()),revision=o.revision,action=action,checklist=list(CHECKLISTS.get(action, {})),production_id=str(o.current_production_id),address_confirmed=True,carrier='测试快递',tracking_number='TEST12345'),format='json')
            self.assertEqual(r.status_code,200,r.data);o.refresh_from_db()
        self.assertEqual(o.state,'shipped')

    def test_free_printing_can_charge_shipping(self):
        self.product.shipping_fen=800;self.product.save();self.body['quote_total_fen']=800
        o=self.create();self.assertEqual(o.total_fen,800);self.assertEqual(o.payment_state,'unpaid')

    def test_free_cancel_does_not_start_refund(self):
        o=self.create();self.assertEqual(self.action(o,'cancel').status_code,200)
        o.refresh_from_db();self.assertEqual(o.refund_state,'');self.assertIsNone(o.transaction_id)

    def test_seed_is_idempotent_and_preserves_existing_settings(self):
        from django.core.management import call_command
        call_command('seed_print_products');count=Product.objects.count()
        seeded=Product.objects.get(width_mm=176,height_mm=250)
        seeded.paper='confirmed paper';seeded.save()
        call_command('seed_print_products');seeded.refresh_from_db()
        self.assertEqual(Product.objects.count(),count);self.assertEqual(seeded.paper,'confirmed paper')
        self.assertTrue(seeded.free_printing);self.assertFalse(seeded.proof_approved)

class OperationsTests(TestCase):
    setUp = PrintTests.setUp
    create = PrintTests.create
    action = PrintTests.action

    def ready(self):
        o=self.create();o.payment_state='not_required';o.total_fen=0;o.file_state='ready';o.state='awaiting_review';o.save()
        p=o.current_production;p.state='ready';p.result={'files':{'archive':{'key':'traveldiary/print/production/a.zip'}}};p.save()
        return o

    def admin_action(self,o,action,**kwargs):
        self.client.force_authenticate(self.admin)
        return self.client.post(f'/api/admin/v1/print/orders/{o.id}/',dict(key=str(uuid.uuid4()),revision=o.revision,action=action,**kwargs),format='json')

    def move(self,o,action,**kwargs):
        r=self.admin_action(o,action,**kwargs);self.assertEqual(r.status_code,200,r.data);o.refresh_from_db();return r

    def checked(self,o,action):
        return self.move(o,action,checklist=list(CHECKLISTS[action]),production_id=str(o.current_production_id))

    def test_checklists_are_required_and_audited(self):
        o=self.ready()
        self.assertEqual(self.admin_action(o,'approve').status_code,400)
        self.checked(o,'approve');self.checked(o,'start');self.checked(o,'finish')
        e=o.events.get(action='finish');self.assertEqual(e.actor,self.admin);self.assertEqual(len(e.details['checklist']),4)
        r=self.client.get(f'/api/admin/v1/print/orders/{o.id}/')
        self.assertEqual(r.data['events'][-1]['actor'],self.admin.username)

    def test_pause_resume_reprint_and_shipping_corrections(self):
        o=self.ready();self.checked(o,'approve');self.checked(o,'start')
        self.move(o,'pause',message='装订设备检修');self.assertEqual(o.state,'paused')
        self.assertEqual(self.admin_action(o,'finish').status_code,409)
        self.move(o,'resume',message='设备恢复');self.assertEqual(o.state,'producing')
        self.move(o,'reprint',message='首张色彩不合格');self.assertEqual(o.state,'queued')
        self.checked(o,'start');self.checked(o,'finish')
        shipping=dict(carrier='顺丰',tracking_number='SF123456',address_confirmed=True)
        self.move(o,'ship',**shipping)
        self.move(o,'correct_shipment',**{**shipping,'tracking_number':'SF654321'},shipment_id=o.shipments.get().id,message='更正录入错误')
        self.assertEqual(o.shipments.get().tracking_number,'SF654321')
        self.move(o,'reship',**shipping,message='运输损坏补寄');self.assertEqual(o.shipments.count(),2)
        self.move(o,'complete',message='已电话核实收到完整成品');self.assertEqual(o.state,'completed')

    def test_after_sale_queue_and_resolution_visible_to_user(self):
        o=self.ready();self.client.force_authenticate(self.user)
        self.assertEqual(self.action(o,'after_sale',message='希望确认配送时间').status_code,200);o.refresh_from_db()
        self.client.force_authenticate(self.admin)
        r=self.client.get('/api/admin/v1/print/orders/?state=after_sale')
        self.assertEqual(r.data['total'],1);self.assertEqual(r.data['counts']['after_sale'],1)
        self.move(o,'accept_after_sale');self.move(o,'resolve_after_sale',message='已沟通按约定时间寄出')
        self.assertEqual(self.client.get('/api/admin/v1/print/orders/?state=after_sale').data['total'],0)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get(f'/api/v1/print/orders/{o.id}/').data['after_sale_resolution'],'已沟通按约定时间寄出')

    def test_cancelled_download_capability_matches_endpoint(self):
        o=self.ready();self.move(o,'cancel')
        self.assertFalse(self.client.get(f'/api/admin/v1/print/orders/{o.id}/').data['can_download'])
        self.assertEqual(self.client.post(f'/api/admin/v1/print/orders/{o.id}/downloads/').status_code,409)

    def test_revision_replaces_current_draft_and_preserves_payment(self):
        o=self.ready();o.payment_state='paid';o.total_fen=1020;o.save();old=o.current_production_id
        self.move(o,'needs_revision',message='请调整第 2 页文字边距')
        self.client.force_authenticate(self.user)
        body={**self.body,'key':str(uuid.uuid4()),'revise_order_id':str(o.id),'order_revision':o.revision}
        self.assertEqual(self.client.post('/api/v1/print/orders/',body,format='json').status_code,200)
        self.assertEqual(self.client.post('/api/v1/print/orders/',body,format='json').status_code,200)
        o.refresh_from_db();self.assertEqual(o.payment_state,'paid');self.assertEqual(o.total_fen,1020);self.assertEqual(o.productions.count(),1)
        self.assertFalse(Production.objects.filter(pk=old).exists())
        self.assertEqual(self.client.post(f'/api/v1/print/orders/{o.id}/upload/',{'production_id':str(old)},format='json').status_code,409)
        result=self.client.post(f'/api/v1/print/orders/{o.id}/complete-upload/',dict(production_id=str(o.current_production_id),client_confirmed=True,completed_roles=['cover','interior']),format='json')
        self.assertEqual(result.status_code,200,result.data);o.refresh_from_db();self.assertEqual(o.state,'awaiting_review')

    def test_revision_rejects_other_owner_and_price_or_page_changes(self):
        o=self.ready();self.move(o,'needs_revision',message='调整文字')
        body={**self.body,'key':str(uuid.uuid4()),'revise_order_id':str(o.id),'order_revision':o.revision,'quote_total_fen':0}
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post('/api/v1/print/orders/',body,format='json').status_code,400) # unbound identity
        self.client.force_authenticate(self.user)
        for change in ({'quantity':2},{'page_count':4},{'quote_total_fen':10}):
            self.assertEqual(self.client.post('/api/v1/print/orders/',{**body,**change},format='json').status_code,400)
        self.assertEqual(Order.objects.count(),1)

    def test_proof_and_opening_require_evidence(self):
        self.client.force_authenticate(self.admin)
        from .views import product_data
        data=product_data(self.product)
        self.assertEqual(self.client.post('/api/admin/v1/print/products/',data,format='json').status_code,400)
        data.update(proof_note='A5 双面实样，页序与装订检查通过',lead_time='审核后 3 天制作')
        r=self.client.post('/api/admin/v1/print/products/',data,format='json');self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data['proof_by'],self.admin.username);self.assertIsNotNone(r.data['proof_at'])
        data.update(revision=r.data['revision'],paper='新纸张')
        self.assertEqual(self.client.post('/api/admin/v1/print/products/',data,format='json').status_code,400)
        data['reproof_confirmed']=True
        self.assertEqual(self.client.post('/api/admin/v1/print/products/',data,format='json').status_code,200)

    def test_stale_admin_action_is_rejected(self):
        o=self.ready();revision=o.revision;self.checked(o,'approve')
        r=self.client.post(f'/api/admin/v1/print/orders/{o.id}/',dict(key=str(uuid.uuid4()),revision=revision,action='start',checklist=list(CHECKLISTS['start']),production_id=str(o.current_production_id)),format='json')
        self.assertEqual(r.status_code,409)


    def test_refund_recheck_schedules_reconciliation_after_commit(self):
        o=self.ready();o.payment_state='refund_pending';o.refund_state='exception';o.save()
        with patch('print_orders.tasks.reconcile_payments.delay') as schedule:
            with self.captureOnCommitCallbacks(execute=True): self.move(o,'refresh_refund')
            schedule.assert_called_once()
        o.refresh_from_db();self.assertEqual(o.refund_state,'processing')


    def test_production_permission_and_ship_validation_fail_closed(self):
        from django.contrib.auth.models import Permission
        o=self.ready();o.state='ready_to_ship';o.save()
        self.other.user_permissions.add(Permission.objects.get(codename='change_order',content_type__app_label='print_orders'))
        self.client.force_authenticate(self.other)
        detail=self.client.get(f'/api/admin/v1/print/orders/{o.id}/').data
        self.assertFalse(detail['can_download']);self.assertNotIn('refund',detail['allowed_actions'])
        self.assertEqual(self.client.post(f'/api/admin/v1/print/orders/{o.id}/downloads/').status_code,400)
        self.assertEqual(self.admin_action(o,'ship',carrier='顺丰',tracking_number='SF12345').status_code,400)
        self.assertEqual(o.shipments.count(),0)

    def test_current_upload_id_is_required_for_completion(self):
        o=self.create()
        self.assertEqual(self.client.post(f'/api/v1/print/orders/{o.id}/complete-upload/',{'production_id':str(uuid.uuid4())},format='json').status_code,409)
        with patch('print_orders.storage.bucket',side_effect=AssertionError('Server must not contact OSS')):
            r=self.client.post(f'/api/v1/print/orders/{o.id}/complete-upload/',{'production_id':str(o.current_production_id),'client_confirmed':True,'completed_roles':['cover','interior']},format='json')
        self.assertEqual(r.status_code,200,r.data);o.refresh_from_db();self.assertEqual(o.file_state,'ready')



class DirectUploadTests(TestCase):
    setUp = PrintTests.setUp
    create = PrintTests.create

    def test_upload_plan_only_signs_and_never_contacts_oss(self):
        from unittest.mock import Mock
        o=self.create();signer=Mock(spec=['sign_url']);signer.sign_url.return_value='https://example.test/signed'
        url=f'/api/v1/print/orders/{o.id}/upload/'
        with patch('print_orders.storage.bucket',return_value=signer):
            r=self.client.post(url,dict(production_id=str(o.current_production_id)),format='json')
            self.assertEqual(r.status_code,200,r.data)
            self.assertEqual(len(r.data['files']),2)
            self.assertTrue(all(f['init_url'] for f in r.data['files']))
            self.assertTrue(all(not f['parts'] for f in r.data['files']))
            r=self.client.post(url,dict(production_id=str(o.current_production_id),uploads={'cover':'client-session-1','interior':'client-session-2'}),format='json')
            self.assertEqual(r.status_code,200,r.data)
            for f in r.data['files']:
                self.assertTrue(f['list_url']);self.assertTrue(f['complete_url'])
                self.assertEqual(f['parts'][0]['headers'],{'Content-Type':'application/octet-stream'})
            calls=signer.sign_url.call_args_list
            self.assertTrue(any(c.args[0]=='POST' and c.kwargs.get('headers')=={'Content-Type':'application/xml'} for c in calls))

    def test_completion_is_offline_idempotent_and_enters_review(self):
        o=self.create();o.payment_state='not_required';o.total_fen=0;o.save()
        data=dict(production_id=str(o.current_production_id),client_confirmed=True,completed_roles=['cover','interior'])
        with patch('print_orders.storage.bucket',side_effect=AssertionError('No OSS allowed')):
            for _ in range(2):
                r=self.client.post(f'/api/v1/print/orders/{o.id}/complete-upload/',data,format='json')
                self.assertEqual(r.status_code,200,r.data)
        o.refresh_from_db();self.assertEqual(o.state,'awaiting_review');self.assertEqual(o.file_state,'ready')
        self.assertEqual(o.events.filter(action='uploaded').count(),1)
        self.assertEqual(set(o.current_production.result['files']),{'cover','interior'})

    def test_completion_keeps_payment_and_ownership_checks(self):
        o=self.create();url=f'/api/v1/print/orders/{o.id}/complete-upload/'
        self.assertEqual(self.client.post(url,dict(production_id=str(o.current_production_id)),format='json').status_code,400)
        data=dict(production_id=str(o.current_production_id),client_confirmed=True,completed_roles=['cover','interior'])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(url,data,format='json').status_code,404)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(url,data,format='json').status_code,200)
        o.refresh_from_db();self.assertEqual(o.state,'draft');self.assertEqual(o.payment_state,'unpaid')
        self.assertEqual(self.client.post('/api/internal/print/processor/',{}).status_code,404)

class OptionalShellTests(TestCase):
    setUp = PrintTests.setUp
    create = PrintTests.create
    def test_no_shell_order_uploads_only_interior_offline(self):
        self.body['snapshot']['pages'] = [p for p in self.body['snapshot']['pages'] if p['role']=='interior']
        self.body['files'] = [f for f in self.body['files'] if f['role']=='interior']
        o = self.create()
        o.payment_state='not_required';o.total_fen=0;o.save()
        with patch('print_orders.storage.bucket', side_effect=AssertionError('No OSS requests')):
            r=self.client.post(f'/api/v1/print/orders/{o.id}/complete-upload/',dict(production_id=str(o.current_production_id),client_confirmed=True,completed_roles=['interior']),format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data['cover_page_count'],0)
        self.assertEqual(r.data['state'],'awaiting_review')
        o.refresh_from_db();self.assertEqual(set(o.current_production.result['files']),{'interior'})

    def test_all_content_including_first_and_last_are_preserved(self):
        pages=[dict(page_id=str(uuid.uuid4()),revision_id=str(uuid.uuid4()),role='interior') for _ in range(3)]
        self.body['snapshot']['pages'] = pages
        self.body['files'] = [dict(role='interior',sha256='b'*64,size=300,page_count=4)]
        self.body['page_count']=4;self.body['quote_total_fen']=1040
        o=self.create()
        self.assertEqual(o.snapshot['pages'],pages)
        self.assertEqual(o.page_count,4)
        self.client.force_authenticate(self.admin)
        r=self.client.get(f'/api/admin/v1/print/orders/{o.id}/')
        self.assertEqual(r.data['cover_page_count'],0)

    def test_shell_is_optional_single_page_and_must_match_manifest(self):
        self.body['files'][1]['page_count']=2
        self.assertEqual(self.client.post('/api/v1/print/orders/',self.body,format='json').status_code,400)
        self.body['files'][1]['page_count']=1
        self.body['snapshot']['pages'].reverse()
        self.assertEqual(self.client.post('/api/v1/print/orders/',self.body,format='json').status_code,400)
        self.body['snapshot']['pages'].reverse()
        self.body['snapshot']['pages'][0]['role']='back'
        self.assertEqual(self.client.post('/api/v1/print/orders/',self.body,format='json').status_code,400)
