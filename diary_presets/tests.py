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
