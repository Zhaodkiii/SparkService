from unittest.mock import patch, Mock
from django.test import SimpleTestCase, RequestFactory, override_settings
from .books import allowed, projection, slots
from django.core.cache import cache
import json

@override_settings(ALLOWED_HOSTS=["localhost", "app.dreamwhale.top", "192.168.31.128"])
class BookPreviewTests(SimpleTestCase):
    def setUp(self):
        self.factory=RequestFactory()
        cache.clear()
    def test_local_scope_does_not_enable_production(self):
        self.assertTrue(allowed(self.factory.get('/',HTTP_HOST='localhost:6028',REMOTE_ADDR='127.0.0.1')))
        self.assertFalse(allowed(self.factory.get('/',HTTP_HOST='app.dreamwhale.top',REMOTE_ADDR='127.0.0.1')))
        self.assertFalse(allowed(self.factory.get('/',HTTP_HOST='192.168.31.128',REMOTE_ADDR='8.8.8.8')))
    @patch('public_experience.books.storage.sign',side_effect=lambda key:'signed:'+key)
    @patch('public_experience.books.storage.bucket')
    @patch('public_experience.books.version')
    def test_projection_only_reads_current_page_dependencies(self,version,bucket,sign):
        version.return_value=(None,Mock(snapshot={'pages':[{'data':{'id':'one','rootContentID':'root'}}], 'manifest':{'objectTable':{'root':'root.json','unvisited':'other.json'},'assetTable':{'a':{'path':'a.png','pixelSize':{'width':10,'height':10}}}},'keys':{'root.json':'root-key','other.json':'other-key','a.png':'image-key'}}))
        bucket.return_value.get_object.return_value.read.return_value=json.dumps({'layers':[{'assetID':'a'}]}).encode()
        bucket.return_value.sign_url.return_value='sized-image-url'
        response=projection(self.factory.get('/'),'book',1,'one')
        self.assertEqual(response.status_code,200)
        bucket.return_value.get_object.assert_called_once_with('root-key')
        self.assertEqual(list(json.loads(response.content)['assets']),['a'])
        bucket.return_value.sign_url.assert_called_once_with('GET','image-key',900,slash_safe=True,params={'x-oss-process':'image/resize,l_2048'})

    @patch('public_experience.books.storage.bucket')
    @patch('public_experience.books.version')
    def test_thumbnails_only_sign_photo_slots(self, version, bucket):
        version.return_value=(None, Mock(snapshot={'pages':[{'data':{'id':'one','rootContentID':'root','editableSlots':[{'kind':'photo','layerID':'photo'}]}}], 'manifest':{'objectTable':{'root':'root.json'},'assetTable':{'a':{'path':'a.png'},'decor':{'path':'decor.png'}}},'keys':{'root.json':'root-key','a.png':'photo-key','decor.png':'decor-key'}}))
        bucket.return_value.get_object.return_value.read.return_value=json.dumps({'layers':[{'id':'photo','assetID':'a'},{'id':'frame','assetID':'decor'}]}).encode()
        bucket.return_value.sign_url.return_value='thumbnail-url'
        response=slots(self.factory.get('/'),'book',1,'one')
        self.assertEqual(json.loads(response.content)['items'],[{'layerId':'photo','url':'thumbnail-url'}])
        bucket.return_value.sign_url.assert_called_once_with('GET','photo-key',900,slash_safe=True,params={'x-oss-process':'image/resize,w_160'})
