import json
import os
import uuid
import base64
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from .models import Product, Order, PaymentChannel, PaymentConfig, PaymentAttempt, PaymentRefund
from . import payments, payment_config as vault, payment_provider as provider, alipay
from .domain import Conflict, Unavailable


class PaymentWorkflowTests(TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'PRINT_PAYMENT_ENCRYPTION_KEY':Fernet.generate_key().decode()});self.env.start();self.addCleanup(self.env.stop)
        self.user=get_user_model().objects.create_user(username='payer')
        self.admin=get_user_model().objects.create_superuser(username='finance',email='finance@example.test',password='test')
        self.client=APIClient();self.client.force_authenticate(self.user)
        self.product=Product.objects.create(title='A5',active=True,proof_approved=True,paper='纸',binding='活页')
        self.order=Order.objects.create(owner=self.user,product=self.product,creation_key=uuid.uuid4(),request_hash='x',spec={},address={},snapshot={},quantity=1,page_count=2,title='支付测试',total_fen=100,file_state='ready')
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048);self.key=key
        self.private={'PRIVATE_KEY':key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode(),'PUBLIC_KEY':key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode(),'API_V3_KEY':'1'*32}
        self.configs={}
        for code in ('wechat','alipay'):
            c=PaymentChannel.objects.create(code=code,enabled=True)
            public={'APPID':'app','MCHID':'merchant','SERIAL':'serial','PUBLIC_KEY_ID':'key','SELLER_ID':'seller','NOTIFY_URL':f'https://example.test/api/v1/print/{code}-notify/'}
            v=PaymentConfig.objects.create(channel=c,public=public,encrypted=vault.encrypt(self.private),actor='test');c.current=v;c.save();self.configs[code]=v
    def attempt(self,channel='wechat',**kwargs):
        return PaymentAttempt.objects.create(order=self.order,config=self.configs[channel],key=uuid.uuid4(),amount=100,expires_at=timezone.now()+timedelta(minutes=30),**kwargs)
    def paid(self,a,identifier='tx1'):return payments.apply_result(a.pk,{'state':'succeeded','provider_id':identifier})
    def test_free_order_does_not_create_trade(self):
        self.order.total_fen=0;self.order.save()
        with self.assertRaises(Conflict):payments.start(self.order.pk,self.user,'alipay',uuid.uuid4())
        self.assertEqual(PaymentAttempt.objects.count(),0)
    def test_owner_guard_and_configuration_permissions(self):
        other=get_user_model().objects.create_user(username='other');self.client.force_authenticate(other)
        self.assertEqual(self.client.post(f'/api/v1/print/orders/{self.order.pk}/payments/',{'channel':'alipay','key':str(uuid.uuid4())},format='json').status_code,404)
        self.assertEqual(self.client.get('/api/admin/v1/print/payments/channels/').status_code,403)
    def test_idempotent_start_and_amount_from_server(self):
        key=uuid.uuid4()
        with patch.object(provider,'create',return_value=({'order_string':'signed'},'')),patch.object(provider,'query',return_value={'state':'pending'}):
            first=payments.start(self.order.pk,self.user,'alipay',key)
            second=payments.start(self.order.pk,self.user,'alipay',key)
        self.assertEqual(first['attempt_id'],second['attempt_id']);self.assertEqual(PaymentAttempt.objects.get().amount,100)
    def test_duplicate_and_late_callback(self):
        a=self.attempt();self.order.state='cancelled';self.order.cancel_requested=True;self.order.save()
        self.paid(a);self.paid(a)
        self.order.refresh_from_db();self.assertEqual(self.order.state,'cancelled');self.assertEqual(self.order.payment_state,'refund_pending')
        self.assertEqual(PaymentRefund.objects.count(),1);self.assertEqual(self.order.events.filter(action='paid').count(),1)
    def test_paid_does_not_review_unready_file(self):
        self.order.file_state='uploading';self.order.save();self.paid(self.attempt())
        self.order.refresh_from_db();self.assertEqual(self.order.state,'draft');self.assertEqual(self.order.payment_state,'paid')
    def test_duplicate_cross_channel_payment_refunds_only_extra(self):
        first=self.attempt();self.paid(first,'tx1');other=self.attempt('alipay');self.paid(other,'tx2')
        self.assertEqual(PaymentRefund.objects.get().attempt,other)
        self.order.refresh_from_db();self.assertEqual(self.order.transaction_id,'wechat:tx1');self.assertEqual(self.order.payment_state,'paid')
    def test_unknown_old_trade_blocks_switch(self):
        a=self.attempt()
        with patch.object(provider,'query',return_value={'state':'absent'}),patch.object(provider,'create') as create:
            with self.assertRaises(Conflict):payments.start(self.order.pk,self.user,'alipay',uuid.uuid4())
            create.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.count(),1)
    def test_switch_after_confirmed_close(self):
        a=self.attempt()
        with patch.object(provider,'query',side_effect=[{'state':'pending'},{'state':'closed'}]),patch.object(provider,'close'),patch.object(provider,'create',return_value=({'order_string':'signed'},'')):
            result=payments.start(self.order.pk,self.user,'alipay',uuid.uuid4())
        a.refresh_from_db();self.assertEqual(a.state,'closed');self.assertEqual(result['channel'],'alipay')
    def test_refund_retry_uses_same_number(self):
        a=self.paid(self.attempt());r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消')
        with patch.object(provider,'refund',side_effect=Unavailable()):
            with self.assertRaises(Unavailable):payments.sync_refund(r.pk)
        r.refresh_from_db();self.assertEqual(r.state,'unknown');self.assertIsNone(r.lease_until)
        with patch.object(provider,'query_refund',return_value={'state':'absent'}),patch.object(provider,'refund',return_value={'state':'success','provider_id':'r1'}) as call: payments.sync_refund(r.pk)
        self.assertEqual(call.call_args.args[0].pk,r.pk)
    def test_disabled_channel_blocks_new_not_old_trade(self):
        a=self.attempt();PaymentChannel.objects.filter(pk='wechat').update(enabled=False)
        with self.assertRaises(Unavailable):payments.start(self.order.pk,self.user,'wechat',uuid.uuid4())
        with patch.object(provider,'query',return_value={'state':'succeeded','provider_id':'ok'}):payments.sync(a.pk)
        a.refresh_from_db();self.assertEqual(a.state,'succeeded')
    def test_config_is_encrypted_and_never_returned(self):
        self.client.force_authenticate(self.admin)
        response=self.client.get('/api/admin/v1/print/payments/channels/')
        self.assertNotIn('BEGIN PRIVATE KEY',str(response.data));self.assertNotIn(self.private['API_V3_KEY'],str(response.data))
        self.assertNotIn('BEGIN PRIVATE KEY',self.configs['wechat'].encrypted)
    def test_config_change_keeps_old_transaction_version(self):
        a=self.attempt();self.client.force_authenticate(self.admin)
        d={'code':'wechat','revision':1,'action':'save','public':{**self.configs['wechat'].public,'APPID':'new'},'environment':'production','secrets':{}}
        response=self.client.post('/api/admin/v1/print/payments/channels/',d,format='json');self.assertEqual(response.status_code,200,response.data)
        a.refresh_from_db();self.assertEqual(a.config.public['APPID'],'app');self.assertEqual(PaymentChannel.objects.get(pk='wechat').current_id,a.config_id)
    def test_bad_amount_and_alipay_signature(self):
        a=self.attempt('alipay')
        values={'out_trade_no':a.id.hex,'trade_no':'t','app_id':'app','seller_id':'seller','trade_status':'TRADE_SUCCESS','total_amount':'0.01','sign_type':'RSA2'}
        values['sign']=base64.b64encode(self.key.sign(alipay.canonical(values).encode(),padding.PKCS1v15(),hashes.SHA256())).decode()
        self.assertEqual(alipay.notification(values,vault.config(a.config)),values)
        with self.assertRaises(ValueError):provider.paid_alipay(a,values)
        with self.assertRaises(ValueError):alipay.notification({**values,'total_amount':'2.00'},vault.config(a.config))
    def test_callback_alipay_idempotent(self):
        a=self.attempt('alipay');values={'out_trade_no':a.id.hex,'trade_no':'t','app_id':'app','seller_id':'seller','trade_status':'TRADE_SUCCESS','total_amount':'1.00','sign_type':'RSA2'}
        values['sign']=base64.b64encode(self.key.sign(alipay.canonical(values).encode(),padding.PKCS1v15(),hashes.SHA256())).decode()
        for _ in range(2):self.assertEqual(self.client.post('/api/v1/print/alipay-notify/',values).status_code,200)
        self.assertEqual(self.order.events.filter(action='paid').count(),1)
    def test_exact_raw_response_is_verified(self):
        cfg=vault.config(self.configs['alipay']);raw='{ "code" : "10000", "trade_status" : "WAIT_BUYER_PAY" }'
        signature=base64.b64encode(self.key.sign(raw.encode(),padding.PKCS1v15(),hashes.SHA256())).decode()
        from unittest.mock import Mock
        response=Mock(content=('{"alipay_trade_query_response":'+raw+',"sign":'+json.dumps(signature)+'}').encode())
        with patch('print_orders.alipay.requests.post',return_value=response):
            self.assertEqual(alipay.request('alipay.trade.query',{},cfg)['trade_status'],'WAIT_BUYER_PAY')

    def test_chinese_refund_declares_charset_before_form_decoding(self):
        from unittest.mock import Mock
        from urllib.parse import parse_qs, urlsplit
        import requests
        cfg=vault.config(self.configs['alipay'])
        raw=json.dumps({'code':'10000','refund_fee':'0.01'},separators=(',',':'))
        signature=base64.b64encode(self.key.sign(raw.encode(),padding.PKCS1v15(),hashes.SHA256())).decode()
        response=Mock(content=json.dumps({'alipay_trade_refund_response':json.loads(raw),'sign':signature},separators=(',',':')).encode())
        biz={'out_trade_no':'test','refund_amount':'0.01','refund_reason':'管理员联调完成自动退款'}
        with patch('print_orders.alipay.requests.post',return_value=response) as post:
            alipay.request('alipay.trade.refund',biz,cfg)
        args,kwargs=post.call_args
        prepared=requests.Request('POST',args[0],params=kwargs['params'],data=kwargs['data'],headers=kwargs['headers']).prepare()
        self.assertEqual(parse_qs(urlsplit(prepared.url).query)['charset'],['utf-8'])
        self.assertIn('charset=utf-8',prepared.headers['Content-Type'])
        fields={k:v[0] for k,v in parse_qs(prepared.body,encoding='utf-8').items()}
        self.assertEqual(json.loads(fields['biz_content']),biz)
        signing='&'.join(f'{k}={fields[k]}' for k in sorted(fields) if k!='sign')
        alipay.verify(signing,fields['sign'],cfg)

    def admin_config(self):
        self.client.force_authenticate(self.admin)
        v=self.configs['alipay'];v.public={**v.public,'APPID':'2021007111664479','SELLER_ID':'2088980621558493'};v.checked_at=timezone.now();v.save();return v

    def test_headerless_keys_normalized_and_field_errors(self):
        raw={k:''.join(v.splitlines()[1:-1]) for k,v in self.private.items() if k!='API_V3_KEY'}
        normalized={k:vault.material(k,v)[0] for k,v in raw.items()}
        self.assertEqual(normalized['PRIVATE_KEY'],self.private['PRIVATE_KEY'])
        self.assertEqual(normalized['PUBLIC_KEY'],self.private['PUBLIC_KEY'])
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError) as error: vault.material('PUBLIC_KEY','bad-public-key')
        self.assertIn('PUBLIC_KEY',error.exception.detail)

    def test_save_checks_before_creating_version_and_does_not_echo_keys(self):
        v=self.admin_config();c=v.channel
        d={'code':'alipay','revision':c.revision,'action':'save','environment':'production','public':v.public,'secrets':{'PUBLIC_KEY':'bad'}}
        response=self.client.post('/api/admin/v1/print/payments/channels/',d,format='json')
        self.assertEqual(response.status_code,400);self.assertEqual(c.versions.count(),1)
        d['secrets']={'PUBLIC_KEY':''.join(self.private['PUBLIC_KEY'].splitlines()[1:-1])}
        response=self.client.post('/api/admin/v1/print/payments/channels/',d,format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data['draft']['materials']['PUBLIC_KEY']['valid'])
        self.assertNotIn(self.private['PRIVATE_KEY'],str(response.data))

    def test_production_and_sandbox_do_not_inherit_secret_material(self):
        v=self.admin_config()
        d={'code':'alipay','revision':v.channel.revision,'action':'save','environment':'sandbox','public':v.public,'secrets':{}}
        response=self.client.post('/api/admin/v1/print/payments/channels/',d,format='json')
        self.assertEqual(response.status_code,400)
        self.assertIn('PRIVATE_KEY',str(response.data))

    def test_cannot_publish_without_explicit_confirmation(self):
        v=self.admin_config()
        response=self.client.post('/api/admin/v1/print/payments/channels/',{'code':'alipay','revision':v.channel.revision,'action':'publish','version_id':v.pk,'verified_note':'仅填写文字不能替代真实联调结果'},format='json')
        self.assertEqual(response.status_code,400)

    def test_probe_permission_token_and_isolation_with_refund(self):
        from .models import PaymentProbe
        from . import payment_probes
        self.client.force_authenticate(self.user)
        url='/api/admin/v1/print/payments/probes/'
        self.assertEqual(self.client.post(url,{'action':'create','version_id':self.configs['alipay'].pk},format='json').status_code,403)
        v=self.admin_config()
        response=self.client.post(url,{'action':'create','version_id':v.pk},format='json')
        self.assertEqual(response.status_code,200,response.data)
        p=PaymentProbe.objects.get();self.assertEqual(p.amount,1)
        launch=f'/api/v1/print/payment-probes/{p.pk}/launch/'
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(launch,{'token':'wrong'},format='json').status_code,400)
        with patch.object(provider,'create',return_value=({'order_string':'signed'},'')):
            self.assertEqual(self.client.post(launch,{'token':str(p.token)},format='json').status_code,200)
        with patch.object(provider,'query',return_value={'state':'succeeded','provider_id':'probe-tx'}),patch.object(provider,'refund',return_value={'state':'success','provider_id':'refund'}) as refund:
            payment_probes.sync(p.pk)
        p.refresh_from_db();self.assertEqual(p.state,'refunded');self.assertEqual(refund.call_args.args[0].id,p.refund_id)
        self.order.refresh_from_db();self.assertEqual(self.order.payment_state,'unpaid');self.assertFalse(self.order.payments.exists())

    def test_probe_late_callback_refunds_after_close_and_publish_with_confirmation(self):
        from .models import PaymentProbe
        from . import payment_probes
        v=self.admin_config()
        p=PaymentProbe.objects.create(config=v,actor='finance',expires_at=timezone.now()-timedelta(minutes=1),state='closed')
        payment_probes.paid(p.pk,{'provider_id':'late'})
        with patch.object(provider,'query',return_value={'state':'succeeded','provider_id':'late'}),patch.object(provider,'refund',return_value={'state':'success','provider_id':'r'}): payment_probes.sync(p.pk)
        p.refresh_from_db();self.assertEqual(p.state,'refunded')
        PaymentProbe.objects.create(config=v,actor='finance',expires_at=timezone.now(),state='closed')
        response=self.client.post('/api/admin/v1/print/payments/channels/',{'code':'alipay','revision':v.channel.revision,'action':'publish','version_id':v.pk,'verified_note':'真机付款退款及取消关单两项验证通过','confirm_enable':True},format='json')
        self.assertEqual(response.status_code,200,response.data)

    def test_probe_link_recovery_is_authorized_and_does_not_create_or_extend(self):
        from .models import PaymentProbe
        self.admin_config();url='/api/admin/v1/print/payments/probes/'
        first=self.client.post(url,{'action':'create','version_id':self.configs['alipay'].pk},format='json')
        p=PaymentProbe.objects.get();expiry=p.expires_at
        again=self.client.post(url,{'action':'create','version_id':p.config_id},format='json')
        recovered=self.client.post(url,{'action':'link','id':str(p.pk)},format='json')
        self.assertEqual(first.data['link'],again.data['link']);self.assertEqual(first.data['link'],recovered.data['link'])
        self.assertEqual(PaymentProbe.objects.count(),1);p.refresh_from_db();self.assertEqual(p.expires_at,expiry)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post(url,{'action':'link','id':str(p.pk)},format='json').status_code,403)
        self.client.force_authenticate(self.admin);p.expires_at=timezone.now()-timedelta(seconds=1);p.save()
        self.assertEqual(self.client.post(url,{'action':'link','id':str(p.pk)},format='json').status_code,409)

    def test_unlaunched_probe_never_queries_gateway_or_counts_as_cancel_test(self):
        from .models import PaymentProbe
        from . import payment_probes
        v=self.admin_config();p=PaymentProbe.objects.create(config=v,actor='finance',expires_at=timezone.now()+timedelta(minutes=10),last_error='old error')
        with patch.object(provider,'query') as query,patch.object(provider,'close') as close:
            payment_probes.sync(p.pk);p.refresh_from_db();self.assertEqual(p.state,'created');self.assertEqual(p.last_error,'')
            payment_probes.sync(p.pk,close=True);p.refresh_from_db();self.assertEqual(p.state,'discarded')
            query.assert_not_called();close.assert_not_called()
        self.assertFalse(v.probes.filter(state='closed').exists())

    def test_expired_unlaunched_probe_can_be_replaced_without_gateway(self):
        from .models import PaymentProbe
        v=self.admin_config();old=PaymentProbe.objects.create(config=v,actor='finance',expires_at=timezone.now()-timedelta(seconds=1))
        with patch.object(provider,'query') as query:
            result=self.client.post('/api/admin/v1/print/payments/probes/',{'action':'create','version_id':v.pk},format='json')
            query.assert_not_called()
        old.refresh_from_db();self.assertEqual(old.state,'expired');self.assertEqual(result.status_code,200)
        self.assertNotEqual(result.data['id'],str(old.pk));self.assertEqual(PaymentProbe.objects.count(),2)

    def test_expired_launched_probe_blocks_new_intent_until_confirmed_closed(self):
        from .models import PaymentProbe
        v=self.admin_config();PaymentProbe.objects.create(config=v,actor='finance',expires_at=timezone.now()-timedelta(seconds=1),state='unknown')
        result=self.client.post('/api/admin/v1/print/payments/probes/',{'action':'create','version_id':v.pk},format='json')
        self.assertEqual(result.status_code,409);self.assertEqual(PaymentProbe.objects.count(),1)

    def test_active_probe_is_returned_even_outside_recent_history(self):
        from .models import PaymentProbe
        v=self.admin_config()
        active=PaymentProbe.objects.create(config=v,actor='finance',expires_at=timezone.now()+timedelta(minutes=10))
        for _ in range(11):PaymentProbe.objects.create(config=v,actor='finance',expires_at=timezone.now(),state='discarded')
        response=self.client.get('/api/admin/v1/print/payments/channels/')
        channel=next(c for c in response.data if c['code']=='alipay')
        self.assertEqual(channel['draft']['active_test']['id'],str(active.pk))
        self.assertNotIn(str(active.pk),[p['id'] for p in channel['draft']['tests']])


    def test_direct_enable_without_tests_or_notes_requires_format_and_is_audited(self):
        from .models import PaymentAudit
        v=self.admin_config()
        d={'code':'alipay','revision':v.channel.revision,'action':'publish','version_id':v.pk,'confirm_enable':True}
        response=self.client.post('/api/admin/v1/print/payments/channels/',d,format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data['enabled']);self.assertFalse(response.data['draft']['test_paid'])
        audit=PaymentAudit.objects.get(action='config_publish')
        self.assertTrue(audit.details['confirmed']);self.assertFalse(audit.details['payment_refund_tested'])
        self.assertFalse(audit.details['close_tested'])

    def test_direct_enable_cannot_bypass_unchecked_or_sandbox_configuration(self):
        v=self.admin_config();v.checked_at=None;v.save()
        d={'code':'alipay','revision':v.channel.revision,'action':'publish','version_id':v.pk,'confirm_enable':True}
        url='/api/admin/v1/print/payments/channels/'
        self.assertEqual(self.client.post(url,d,format='json').status_code,400)
        v.checked_at=timezone.now();v.environment='sandbox';v.save()
        self.assertEqual(self.client.post(url,d,format='json').status_code,400)

    def test_refund_query_never_submits_even_if_no_channel_refund_exists(self):
        a=self.paid(self.attempt('alipay'));r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消')
        self.client.force_authenticate(self.admin)
        with patch.object(provider,'query_refund',return_value={'state':'absent'}),patch.object(provider,'refund') as submit:
            response=self.client.post('/api/admin/v1/print/payments/refunds/',{'id':str(r.pk),'action':'query'},format='json')
        self.assertEqual(response.status_code,200,response.data);submit.assert_not_called()
        r.refresh_from_db();self.assertEqual(r.state,'pending');self.assertFalse(r.submission_started)

    def test_balance_rejection_is_actionable_and_remains_scheduled_beyond_ten_attempts(self):
        from .payment_errors import alipay_error
        a=self.paid(self.attempt('alipay'));r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消',failure_count=12)
        with patch.object(provider,'refund',side_effect=alipay_error('ACQ.SELLER_BALANCE_NOT_ENOUGH')):
            with self.assertRaises(Unavailable): payments.sync_refund(r.pk)
        r.refresh_from_db();self.order.refresh_from_db()
        self.assertEqual(r.state,'blocked');self.assertEqual(r.error_category,'balance');self.assertEqual(r.retry_mode,'auto')
        self.assertIn('余额不足',r.last_error);self.assertIn('补足',r.recovery_action)
        self.assertGreater(r.next_check_at,timezone.now()+timedelta(hours=5));self.assertEqual(self.order.refund_state,'blocked')

    def test_unknown_retry_queries_prior_refund_and_never_resubmits_confirmed_success(self):
        a=self.paid(self.attempt('alipay'));r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消',state='unknown',submission_started=True)
        with patch.object(provider,'query_refund',return_value={'state':'success','provider_id':'already-refunded'}),patch.object(provider,'refund') as submit:
            payments.sync_refund(r.pk,action='retry',actor='finance')
        r.refresh_from_db();self.order.refresh_from_db();submit.assert_not_called()
        self.assertEqual(r.state,'success');self.assertIsNotNone(r.completed_at);self.assertEqual(self.order.payment_state,'refunded')

    def test_processing_refund_is_queried_without_resubmitting(self):
        a=self.paid(self.attempt('alipay'));r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消',state='processing',submission_started=True)
        with patch.object(provider,'query_refund',return_value={'state':'processing','provider_id':'tx'}),patch.object(provider,'refund') as submit:
            payments.sync_refund(r.pk)
        submit.assert_not_called();r.refresh_from_db();self.assertEqual(r.state,'processing')

    def test_pause_resume_and_technical_failure_limit(self):
        a=self.paid(self.attempt('alipay'));r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消',failure_count=9)
        with patch.object(provider,'refund',side_effect=Unavailable()):
            with self.assertRaises(Unavailable): payments.sync_refund(r.pk)
        r.refresh_from_db();self.assertEqual(r.retry_mode,'paused');self.assertIsNone(r.next_check_at)
        with patch.object(provider,'refund') as submit: payments.sync_refund(r.pk)
        submit.assert_not_called()
        with patch.object(provider,'query_refund',return_value={'state':'absent'}),patch.object(provider,'refund',return_value={'state':'success','provider_id':'refunded'}):
            payments.sync_refund(r.pk,action='resume')
        r.refresh_from_db();self.assertEqual(r.retry_mode,'auto');self.assertEqual(r.state,'success')

    def test_alipay_refund_requires_fund_change_or_verified_query(self):
        a=self.paid(self.attempt('alipay'),'alipay-transaction');r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消')
        data={'out_trade_no':a.id.hex,'trade_no':a.provider_id,'refund_fee':'1.00','fund_change':'N'}
        with patch.object(alipay,'request',return_value=data),patch.object(provider,'query_refund',return_value={'state':'processing','provider_id':'tx'}) as query:
            self.assertEqual(provider.refund(r)['state'],'processing')
        query.assert_called_once()
        data.pop('fund_change')
        with patch.object(alipay,'request',return_value=data),patch.object(provider,'query_refund',return_value={'state':'success','provider_id':'tx'}) as query:
            self.assertEqual(provider.refund(r)['state'],'success')
        query.assert_called_once()
        data['fund_change']='Y'
        with patch.object(alipay,'request',return_value=data),patch.object(provider,'query_refund') as query:
            self.assertEqual(provider.refund(r)['state'],'success')
        query.assert_not_called()

    def test_alipay_empty_refund_query_is_not_a_success(self):
        a=self.paid(self.attempt('alipay'));r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消')
        with patch.object(alipay,'request',return_value={'code':'10000','out_trade_no':a.id.hex}):
            self.assertEqual(provider.query_refund(r)['state'],'absent')

    def test_provider_business_errors_keep_safe_codes_without_echoing_arbitrary_details(self):
        from unittest.mock import Mock
        cfg=vault.config(self.configs['alipay'])
        raw=json.dumps({'code':'40004','sub_code':'ACQ.SELLER_BALANCE_NOT_ENOUGH','sub_msg':'sensitive echoed material'},separators=(',',':'))
        signature=base64.b64encode(self.key.sign(raw.encode(),padding.PKCS1v15(),hashes.SHA256())).decode()
        response=Mock(content=('{"alipay_trade_refund_response":'+raw+',"sign":'+json.dumps(signature)+'}').encode())
        with patch.object(alipay.requests,'post',return_value=response):
            with self.assertRaises(Unavailable) as e: alipay.request('alipay.trade.refund',{},cfg)
        self.assertEqual(e.exception.gateway_code,'ACQ.SELLER_BALANCE_NOT_ENOUGH');self.assertNotIn('sensitive',str(e.exception))

    def test_payment_view_query_and_refund_permissions_are_separate(self):
        from django.contrib.auth.models import Permission
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='print_orders',codename='view_paymentattempt'))
        a=self.paid(self.attempt('alipay'));r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消')
        self.assertEqual(self.client.get('/api/admin/v1/print/payments/transactions/').status_code,200)
        self.assertEqual(self.client.post('/api/admin/v1/print/payments/refunds/',{'id':str(r.pk),'action':'query'},format='json').status_code,403)
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='print_orders',codename='query_payment'))
        self.client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
        with patch.object(provider,'query_refund',return_value={'state':'absent'}):
            self.assertEqual(self.client.post('/api/admin/v1/print/payments/refunds/',{'id':str(r.pk),'action':'query'},format='json').status_code,200)
        self.assertEqual(self.client.post('/api/admin/v1/print/payments/refunds/',{'id':str(r.pk),'action':'retry','confirmed':True},format='json').status_code,403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post('/api/admin/v1/print/payments/refunds/',{'id':str(r.pk),'action':'retry'},format='json').status_code,400)

    def test_refund_filters_overview_and_linked_records(self):
        self.client.force_authenticate(self.admin)
        a=self.paid(self.attempt('alipay'));r=PaymentRefund.objects.create(attempt=a,amount=100,reason='取消',state='blocked',error_category='balance',retry_mode='paused')
        response=self.client.get('/api/admin/v1/print/payments/refunds/',{'q':self.order.id.hex.upper(),'channel':'alipay','error_category':'balance','queue':'paused'})
        self.assertEqual(response.data['count'],1);self.assertEqual(response.data['results'][0]['id'],str(r.pk))
        t=self.client.get('/api/admin/v1/print/payments/transactions/',{'q':str(self.order.pk)})
        self.assertEqual(t.data['results'][0]['refund']['state'],'blocked')
        stats=self.client.get('/api/admin/v1/print/payments/overview/').data
        self.assertEqual(stats['blocked'],1);self.assertEqual(stats['paused'],1);self.assertEqual(stats['outstanding_refund_fen'],100);self.assertFalse(stats['settlement_available'])
        self.assertEqual(self.client.get('/api/admin/v1/print/payments/refunds/',{'date_from':'invalid'}).status_code,400)

    def test_audit_paginates_all_history_and_includes_failures(self):
        self.client.force_authenticate(self.admin)
        for i in range(105): payments.audit('refund_query',self.order.pk,'finance',result='failed' if i%2 else 'success',before='blocked',after='blocked')
        response=self.client.get('/api/admin/v1/print/payments/audit/',{'q':str(self.order.pk),'page':4})
        self.assertEqual(response.data['count'],105);self.assertEqual(len(response.data['results']),15)
        filtered=self.client.get('/api/admin/v1/print/payments/audit/',{'q':str(self.order.pk),'result':'failed'})
        self.assertEqual(filtered.data['count'],52)

    def test_expired_absent_probe_does_not_claim_gateway_close_verification(self):
        from .models import PaymentProbe
        from . import payment_probes
        v=self.admin_config();p=PaymentProbe.objects.create(config=v,actor='finance',state='pending',expires_at=timezone.now()-timedelta(seconds=1))
        with patch.object(provider,'query',return_value={'state':'absent'}),patch.object(provider,'close') as close: payment_probes.sync(p.pk)
        close.assert_not_called();p.refresh_from_db();self.assertEqual(p.close_kind,'expired_absent')
        data=self.client.get('/api/admin/v1/print/payments/channels/').data[0]['draft']
        self.assertFalse(data['test_closed']);self.assertTrue(data['test_expired'])

    def test_terminal_payment_does_not_advertise_a_scheduled_poll(self):
        from .payment_admin import transaction_data
        a=self.paid(self.attempt('alipay'))
        a.next_check_at=timezone.now()+timedelta(minutes=1);a.save()
        self.assertIsNone(transaction_data(a)['next_check_at'])
