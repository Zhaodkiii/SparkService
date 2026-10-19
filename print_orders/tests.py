import json
import uuid
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from accounts.models import SocialIdentity
from .models import Product, Order, Shipment, Production, FileCleanup
from .services import apply_payment
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
    def test_late_payment_never_restarts_cancelled_order(self):
        o=self.create();o.state='cancelled';o.cancel_requested=True;o.save()
        result=dict(trade_state='SUCCESS',mchid='m',appid='a',out_trade_no=o.id.hex,transaction_id='wx1',amount=dict(total=1020,currency='CNY'))
        with patch('print_orders.wechat.config',return_value={'MCHID':'m','APPID':'a'}):
            apply_payment(o,result);apply_payment(o,result)
        o.refresh_from_db();self.assertEqual(o.state,'cancelled');self.assertEqual(o.payment_state,'refund_pending')
        self.assertEqual(o.events.filter(action='paid').count(),1)
    def test_wrong_payment_amount_rejected(self):
        o=self.create()
        with patch('print_orders.wechat.config',return_value={'MCHID':'m','APPID':'a'}):
            from rest_framework.exceptions import ValidationError
            with self.assertRaises(ValidationError):apply_payment(o,dict(trade_state='SUCCESS',mchid='m',appid='a',out_trade_no=o.id.hex,transaction_id='wx',amount=dict(total=1,currency='CNY')))
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


    def test_refund_recheck_queries_existing_refund_and_records_success(self):
        o=self.ready();o.state='cancelled';o.total_fen=1020;o.transaction_id='wx-existing';o.cancel_requested=True
        o.payment_state='refund_pending';o.refund_state='exception';o.save()
        result={'out_refund_no':'R'+o.id.hex,'out_trade_no':o.id.hex,'amount':{'refund':1020,'total':1020},'status':'SUCCESS'}
        with patch('print_orders.wechat.query_refund',return_value=result) as query, patch('print_orders.wechat.refund') as refund:
            self.move(o,'refresh_refund');query.assert_called_once();refund.assert_not_called()
        self.assertEqual(o.payment_state,'refunded');self.assertEqual(o.refund_state,'success')

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
