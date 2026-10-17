from copy import deepcopy
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .domain import select
from .models import Series, Template, DownloadPlan
from .views import publish


def snapshot():
    return {'manifest': {'pages':[{'id':'a','path':'a.json'},{'id':'b','path':'b.json'}],
        'objectTable':{'a':'oa.json','b':'ob.json'}, 'assetTable':{'shared':{'path':'shared.png'}},
        'files':[{'path':p,'byteCount':1,'sha256':'a'*64} for p in ['a.json','b.json','oa.json','ob.json','shared.png']],
        'coverPageID':'a','pageSize':{'width':100,'height':100},'requiredCapabilities':[]},
        'pages':[{'data':{'id':p,'title':p},'files':[p+'.json','o'+p+'.json','shared.png']} for p in ['a','b']],
        'keys':{p:'traveldiary/presets/blobs/'+p for p in ['a.json','b.json','oa.json','ob.json','shared.png']}}


class PresetTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='reader',password='test')
        self.admin=get_user_model().objects.create_superuser(username='publisher',password='test',email='test@example.com')
        self.series=Series.objects.create(slug='islands',title='海岛')
        self.template=Template.objects.create(series=self.series,title='test',draft=snapshot())
        publish(self.template,self.admin)
        self.client=APIClient()

    def test_partial_closure_excludes_other_page(self):
        part=select(snapshot(),['b'])
        self.assertEqual(set(part['keys']), {'b.json','ob.json','shared.png'})
        self.assertEqual(part['manifest']['coverPageID'],'b')
        self.assertEqual(set(part['manifest']['objectTable']), {'b'})

    def test_publish_does_not_mutate_old_version(self):
        old=self.template.current
        self.template.draft=select(self.template.draft,['b'])
        publish(self.template,self.admin)
        old.refresh_from_db()
        self.assertEqual(len(old.snapshot['pages']),2)
        self.assertEqual(self.template.current.number,2)

    def test_reader_cannot_publish(self):
        self.client.force_authenticate(self.user)
        response=self.client.post(f'/api/admin/v1/diary-presets/templates/{self.template.id}/publish/',{'revision':1},format='json')
        self.assertEqual(response.status_code,403)

    def test_plan_and_sign_are_owner_scoped(self):
        self.client.force_authenticate(self.user)
        response=self.client.post(f'/api/v1/diary-presets/templates/{self.template.id}/1/',{'page_ids':['b']},format='json')
        self.assertEqual(response.status_code,201)
        pid=response.data['id']
        with patch('diary_presets.storage.sign',return_value='https://example.oss-cn-beijing.aliyuncs.com/resource'):
            self.assertEqual(self.client.post(f'/api/v1/diary-presets/plans/{pid}/urls/',{'paths':['a.json']},format='json').status_code,400)
            self.assertEqual(self.client.post(f'/api/v1/diary-presets/plans/{pid}/urls/',{'paths':['b.json']},format='json').status_code,200)
            self.client.force_authenticate(self.admin)
            self.assertEqual(self.client.post(f'/api/v1/diary-presets/plans/{pid}/urls/',{'paths':['b.json']},format='json').status_code,404)

    def test_stale_editor_cannot_reorder(self):
        self.client.force_authenticate(self.admin)
        url=f'/api/admin/v1/diary-presets/templates/{self.template.id}/pages/'
        response=self.client.put(url,{'revision':0,'page_ids':['b','a']},format='json')
        self.assertEqual(response.status_code,409)

    def test_invalid_page_and_empty_book_rejected(self):
        for ids in [[], ['unknown'], ['a','a']]:
            with self.assertRaises(ValueError): select(snapshot(),ids)

    def test_processor_requires_secret(self):
        response=self.client.post('/api/internal/diary-presets/processor/',{'action':'claim'},format='json')
        self.assertEqual(response.status_code,403)

    def test_admin_upload_list_is_a_plain_array_and_scoped_to_template(self):
        from .models import Upload
        Upload.objects.create(template=self.template,actor=self.admin,revision=1,
                              object_key='staging/test.zip',size=1)
        self.client.force_authenticate(self.admin)
        response=self.client.get('/api/admin/v1/diary-presets/uploads/',{'template':str(self.template.id)})
        self.assertEqual(response.status_code,200)
        self.assertIsInstance(response.data,list)
        self.assertEqual(len(response.data),1)
        self.assertNotIn('object_key',response.data[0])

    def test_series_plain_response_contains_published_series(self):
        self.client.force_authenticate(self.admin)
        response=self.client.get('/api/admin/v1/diary-presets/series/')
        self.assertEqual(response.status_code,200)
        self.assertIsInstance(response.data,list)
        self.assertEqual(response.data[0]['slug'],'islands')


class BrowseTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = get_user_model().objects.create_user(username='browser')
        series = Series.objects.create(slug='browse', title='Browse')
        snap = snapshot()
        for page in snap['pages']:
            page['data']['preview'] = {'thumbnailPath': 'shared.png', 'largePath': 'shared.png'}
        self.template = Template.objects.create(series=series, title='Browse', draft=snap)
        publish(self.template, self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f'/api/v1/diary-presets/templates/{self.template.id}/1/browse/'

    @patch('diary_presets.storage.sign', return_value='https://example.test/thumb')
    def test_browse_omits_import_data_and_reuses_signed_response(self, sign):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        first = self.client.get(self.url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(set(first.data), {'title', 'page_size', 'cover_page_id', 'shell_page_id', 'expires_at', 'pages'})
        self.assertEqual(len(first.data['pages']), 2)
        self.assertNotIn('manifest', first.data)
        self.assertNotIn('page_data', first.data)
        count = sign.call_count
        with CaptureQueriesContext(connection) as queries:
            second = self.client.get(self.url, HTTP_IF_NONE_MATCH=first['ETag'])
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.content, b'')
        self.assertEqual(sign.call_count, count)
        self.assertTrue(all('"snapshot"' not in q['sql'] for q in queries))
        self.assertIn('private', first['Cache-Control'])

    @patch('diary_presets.storage.sign', return_value='https://example.test/thumb')
    def test_expiry_rotates_etag_even_when_signer_returns_same_url(self, sign):
        with patch('diary_presets.views.time.time', return_value=1800000010):
            first = self.client.get(self.url)
        with patch('diary_presets.views.time.time', return_value=1800000310):
            second = self.client.get(self.url, HTTP_IF_NONE_MATCH=first['ETag'])
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first['ETag'], second['ETag'])
        self.assertGreater(second.data['expires_at'], first.data['expires_at'])

    @patch('diary_presets.storage.sign', return_value='https://example.test/thumb')
    def test_cached_browse_still_checks_visibility_and_auth(self, sign):
        first = self.client.get(self.url)
        self.template.active = False
        self.template.save(update_fields=['active'])
        self.assertEqual(self.client.get(self.url, HTTP_IF_NONE_MATCH=first['ETag']).status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, [401, 403])

    @patch('diary_presets.storage.sign', return_value='https://example.test/thumb')
    def test_new_version_has_separate_cache_and_preserves_download_plan(self, sign):
        first = self.client.get(self.url)
        self.template.title = 'Second version'
        publish(self.template, self.user)
        second = self.client.get(self.url.replace('/1/', '/2/'), HTTP_IF_NONE_MATCH=first['ETag'])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['title'], 'Second version')
        plan = self.client.post(self.url.replace('/browse/', '/'), {'page_ids': ['b']}, format='json')
        self.assertEqual(plan.status_code, 201)
        self.assertIn('files', plan.data['manifest'])
        self.assertEqual([p['id'] for p in plan.data['manifest']['pages']], ['b'])
