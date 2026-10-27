import copy
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from regions.dataset import validate,normalize,canonical,sha
from regions.models import RegionDataset,RegionState,RegionSyncRun
from regions.services import stage,publish,normalize_address,RegionError
from regions.sync import synchronize,acquire,reserve,SyncError
from print_orders.models import Product
import print_orders.tests as print_fixtures

SEED=json.loads((Path(__file__).parent/'data/mainland-regions.json').read_text())

class RegionFixture:
    def setUp(self):
        self.data,_=stage(SEED['regions']);publish(self.data.version,'test','initial reviewed fixture')
    def address(self,**kw):
        return dict(name='test',phone='13800000000',detail='测试街道1号',region='中国大陆',region_version=self.data.version,
                    province_code='330000',city_code='330100',district_code='330106',**kw)
class RegionTests(RegionFixture, TestCase):
    def test_manifest_etag_and_immutable_artifact(self):
        first=self.client.get('/api/v1/regions/manifest/');self.assertEqual(first.status_code,200)
        info=first.json();self.assertIn('structured_print_address_v1',info['capabilities'])
        cached=self.client.get('/api/v1/regions/manifest/',HTTP_IF_NONE_MATCH=first['ETag'])
        self.assertEqual(cached.status_code,304)
        data=self.client.get(info['download_url']);self.assertEqual(data.status_code,200)
        self.assertEqual(sha(data.content.decode()),info['sha256']);self.assertEqual(len(data.content),info['byte_size'])
        state=RegionState.objects.get(pk=1);state.last_checked_at=timezone.now();state.save()
        self.assertEqual(self.client.get('/api/v1/regions/manifest/',HTTP_IF_NONE_MATCH=first['ETag']).status_code,304)
    def test_invalid_path_and_virtual_codes_are_rejected(self):
        for changes in [dict(city_code='310100'),dict(district_code=None),dict(city_code='group:330000')]:
            address=self.address();address.update(changes)
            with self.assertRaises(RegionError):normalize_address(address)
    def test_real_special_paths(self):
        for province,city,district in [('110000',None,'110101'),('410000',None,'419001'),('440000','441900',None)]:
            a=self.address();a.update(province_code=province,city_code=city,district_code=district)
            result=normalize_address(a);self.assertTrue(result['formatted_address']);self.assertNotIn('group:',result['formatted_address'])
    def test_shipping_scope_is_checked_not_trusted(self):
        p=Product(title='test',regions=['上海'])
        with self.assertRaises(RegionError):normalize_address(self.address(),p)
        p.regions=['中国大陆'];self.assertEqual(normalize_address(self.address(),p)['region'],'中国大陆')
        p.regions=['浙江'];self.assertEqual(normalize_address(self.address(),p)['region'],'浙江')
    def test_rename_accepted_but_parent_move_requires_confirmation(self):
        nodes=copy.deepcopy(SEED['regions'])
        for n in nodes:
            if n['code']=='330106':n['name']='测试新名称'
        newer,_=stage(nodes);publish(newer.version,'test','rename')
        self.assertEqual(normalize_address(self.address())['district_name'],'测试新名称')
        for n in nodes:
            if n['code']=='330106':n['parent_code']='330200'
        moved,_=stage(nodes);publish(moved.version,'test','move')
        with self.assertRaises(RegionError):normalize_address(self.address())
    def test_rollback_sequence_and_no_change_deduplication(self):
        same,changed=stage(SEED['regions']);self.assertFalse(changed);self.assertEqual(same.pk,self.data.pk)
        nodes=copy.deepcopy(SEED['regions']);nodes[-1]['name']='test new'
        newer,_=stage(nodes);publish(newer.version,'test','new')
        state=publish(self.data.version,'test','rollback');self.assertEqual(state.release_sequence,3)
        self.assertEqual(state.current_id,self.data.pk)
    def test_corrupt_or_partial_dataset_not_accepted(self):
        for nodes in [SEED['regions'][:30],SEED['regions']+[SEED['regions'][0]]]:
            with self.assertRaises(ValueError):validate(nodes)
    @override_settings(REGIONS_DAILY_REQUEST_BUDGET=1)
    def test_lock_budget_and_due_date(self):
        token=acquire();self.assertTrue(token);self.assertIsNone(acquire(force=True))
        reserve(token)
        with self.assertRaises(SyncError):reserve(token)
        state=RegionState.objects.get(pk=1);state.lock_until=timezone.now()-timedelta(seconds=1);state.next_check_at=timezone.now()+timedelta(days=30);state.save()
        self.assertIsNone(acquire());self.assertTrue(acquire(force=True))
    @override_settings(AMAP_WEB_SERVICE_KEY='test-secret',REGIONS_DAILY_REQUEST_BUDGET=4)
    @patch('regions.sync.requests.get')
    def test_sync_failure_keeps_current_and_never_leaks_key(self,get):
        import requests
        get.side_effect=requests.ConnectionError('https://example.test?key=test-secret')
        run=synchronize(force=True)
        self.assertEqual(run.status,'failed');self.assertNotIn('secret',run.error_code)
        self.assertEqual(RegionState.objects.get(pk=1).current_id,self.data.pk)
        get.reset_mock();self.assertIsNone(synchronize());get.assert_not_called()
    def test_candidates_are_not_public(self):
        nodes=copy.deepcopy(SEED['regions']);nodes[-1]['name']='candidate'
        data,_=stage(nodes)
        self.assertEqual(self.client.get(f'/api/v1/regions/datasets/{data.pk}.json').status_code,404)

class StructuredPrintTests(print_fixtures.PrintTests):
    def setUp(self):
        super().setUp()
        self.dataset,_=stage(SEED['regions']);publish(self.dataset.version,'test','initial')
        self.body['address'].update(region_version=self.dataset.version,province_code='310000',city_code=None,district_code='310101')
    def test_idempotent_replay_after_region_update_keeps_snapshot(self):
        order=self.create();original=order.address.copy()
        nodes=copy.deepcopy(SEED['regions'])
        for n in nodes:
            if n['code']=='310101':n['name']='renamed'
        data,_=stage(nodes);publish(data.version,'test','rename')
        response=self.client.post('/api/v1/print/orders/',self.body,format='json')
        self.assertEqual(response.status_code,200);order.refresh_from_db();self.assertEqual(order.address,original)
    def test_quote_and_create_reject_wrong_region(self):
        self.body['address']['district_code']='330106'
        r=self.client.post('/api/v1/print/quotes/',dict(product_id=str(self.product.pk),page_count=2,quantity=1,region='上海',address=self.body['address']),format='json')
        self.assertEqual(r.status_code,409)
        r=self.client.post('/api/v1/print/orders/',self.body,format='json');self.assertEqual(r.status_code,409)

class RegionSyncSuccessTests(RegionFixture, TestCase):
    @override_settings(AMAP_WEB_SERVICE_KEY='test-key',REGIONS_DAILY_REQUEST_BUDGET=4)
    @patch('regions.sync.requests.get')
    def test_complete_sync_unchanged_and_candidate_require_review(self,get):
        def raw_response(nodes):
            raw={n['code']:dict(adcode=n['code'],name=n['name'],level=n['level'],districts=[]) for n in nodes}
            roots=[]
            for n in nodes:
                if n['parent_code']:raw[n['parent_code']]['districts'].append(raw[n['code']])
                else:roots.append(raw[n['code']])
            return dict(status='1',count='1',districts=[dict(adcode='100000',name='中国',level='country',districts=roots)])
        response=MagicMock();response.status_code=200
        response.__enter__.return_value=response
        response.iter_content.return_value=[json.dumps(raw_response(SEED['regions'])).encode()]
        get.return_value=response
        first=synchronize(force=True);self.assertEqual(first.status,'unchanged')
        nodes=copy.deepcopy(SEED['regions']);nodes[-1]['name']='new candidate'
        response.iter_content.return_value=[json.dumps(raw_response(nodes)).encode()]
        second=synchronize(force=True);self.assertEqual(second.status,'candidate')
        self.assertEqual(RegionState.objects.get(pk=1).current_id,self.data.pk)
        self.assertEqual(RegionDataset.objects.get(pk=second.dataset_version).status,'candidate')
    def test_bootstrap_is_idempotent_and_does_not_override_current(self):
        from django.core.management import call_command
        from io import StringIO
        before=RegionState.objects.get(pk=1).release_sequence
        call_command('regions','bootstrap',stdout=StringIO())
        call_command('regions','bootstrap',stdout=StringIO())
        state=RegionState.objects.get(pk=1)
        self.assertEqual(state.current_id,self.data.pk);self.assertEqual(state.release_sequence,before)
    def test_structured_error_has_stable_recovery_payload(self):
        from regions.services import RegionError
        from common.exception_handlers import api_exception_handler
        result=api_exception_handler(RegionError('REGION_RESELECT_REQUIRED','请重新选择'),{})
        self.assertEqual(result.status_code,409)
        self.assertEqual(result.data['msg'],'请重新选择')
        self.assertEqual(result.data['data']['region_error'],'REGION_RESELECT_REQUIRED')
