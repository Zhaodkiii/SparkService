from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from diary_presets.models import Series, Template, Version
from .models import *
from .services import revision, publish_library


class LibraryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='materials',password='unused')
        self.client=APIClient();self.client.force_authenticate(self.user)
        series=Series.objects.create(slug='city',title='城市系列')
        template=Template.objects.create(series=series,title='苏州')
        template.current=Version.objects.create(template=template,number=1,snapshot={});template.save()
        self.lib=MaterialLibrary.objects.create(template=template,library_type='sticker',title='苏州贴纸库')
        blob=ResourceBlob.objects.create(sha256='a'*64,object_key='traveldiary/presets/blobs/sha256/'+'a'*64,byte_size=12,width=10,height=10,mime='image/png')
        material=Material.objects.create(source_identity='suzhou:note',material_type='sticker')
        self.r=revision(material,dict(name='空白便签',kind='paper',subcategory='note',keywords=['纸卡'],aliases=['便条'],resource_id=blob.pk,thumbnail_id=blob.pk,sources=[]))
        self.v=publish_library(self.lib,[self.r],0)

    def test_publication_idempotent_and_conflict(self):
        self.assertEqual(publish_library(self.lib,[self.r],1).pk,self.v.pk)
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):publish_library(self.lib,[],0)
        self.assertEqual(self.lib.versions.count(),1)

    def test_favorites_are_unique_and_removed_with_account(self):
        path=f'/api/v1/materials/libraries/{self.lib.pk}/favorite/'
        for _ in range(2):self.assertEqual(self.client.post(path,{'favorite':True},format='json').data['favorite_count'],1)
        self.assertEqual(self.client.post(path,{'favorite':False},format='json').data['favorite_count'],0)
        self.client.post(path,{'favorite':True},format='json');self.user.delete()
        self.assertEqual(self.lib.favorites.count(),0)

    @patch('material_library.views.sign',return_value='https://example.test/asset')
    def test_search_and_background_isolation(self,_):
        response=self.client.get(f'/api/v1/materials/libraries/{self.lib.pk}/items/?q=便条')
        self.assertEqual(response.status_code,200);self.assertEqual(len(response.data['items']),1)
        self.assertEqual(self.client.get('/api/v1/materials/libraries/?type=background').data,[])
        self.lib.active=False;self.lib.save()
        self.assertEqual(self.client.post(f'/api/v1/materials/revisions/{self.r.pk}/download/').status_code,400)

    def test_non_admin_cannot_publish(self):
        self.assertEqual(self.client.post(f'/api/v1/materials/manage/{self.lib.template_id}/',{},format='json').status_code,403)

    @patch('material_library.views.sign',return_value='https://example.test/asset')
    def test_global_search_deduplicates_shared_material(self,_):
        other=MaterialLibrary.objects.create(template=self.lib.template,library_type='background',title='背景')
        # Type safety forbids putting a sticker into a background library.
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):publish_library(other,[self.r],0)
        other.delete()
        t=Template.objects.create(series=self.lib.template.series,title='上海')
        t.current=Version.objects.create(template=t,number=1,snapshot={});t.save()
        lib=MaterialLibrary.objects.create(template=t,library_type='sticker',title='上海贴纸库')
        publish_library(lib,[self.r],0)
        result=self.client.get('/api/v1/materials/items/?type=sticker&q=便条')
        self.assertEqual(result.status_code,200);self.assertEqual(len(result.data['items']),1)
        self.assertEqual(self.client.post(f'/api/v1/materials/revisions/{self.r.pk}/download/').status_code,200)

    @patch('material_library.views.sign',return_value='https://example.test/asset')
    def test_old_version_immutable_and_favorite_identity_survives(self,_):
        LibraryFavorite.objects.create(user=self.user,library=self.lib)
        r=revision(self.r.material,dict(name='新名称',kind='paper',subcategory='note',keywords=['纸卡'],aliases=[],resource_id=self.r.resource_id,thumbnail_id=self.r.thumbnail_id,sources=[]))
        publish_library(self.lib,[r],1)
        result=self.client.get(f'/api/v1/materials/libraries/{self.lib.pk}/items/?version=1')
        self.assertEqual(result.data['items'][0]['name'],'空白便签')
        self.assertEqual(self.lib.favorites.count(),1)
        self.assertEqual(ResourceBlob.objects.count(),1)

class LegacyExtractionTests(TestCase):
    def test_legacy_background_and_only_published_pages(self):
        import tempfile, json, hashlib, io
        from pathlib import Path
        from types import SimpleNamespace
        from PIL import Image
        from .extraction import collect
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            image=Image.new('RGBA',(4,4),(0,0,0,0));image.putpixel((1,1),(255,0,0,255))
            stream=io.BytesIO();image.save(stream,format='PNG');data=stream.getvalue();digest=hashlib.sha256(data).hexdigest()
            (root/'asset.png').write_bytes(data)
            manifest={'assetTable':{'asset':{'path':'asset.png','sha256':digest}},'objectTable':{},'pages':[]}
            for key,name in [('kept','背景_海水纸张'),('removed','组件_蓝色渡船插画')]:
                obj={'role':'sticker','layers':[{'id':key,'name':name,'kind':'sticker','assetID':'asset'}]}
                (root/(key+'.json')).write_text(json.dumps(obj))
                manifest['objectTable'][key]=key+'.json'
                page={'id':key,'rootContentID':key};(root/(key+'-page.json')).write_text(json.dumps(page))
                manifest['pages'].append({'path':key+'-page.json'})
            (root/'package.json').write_text(json.dumps(manifest))
            template=SimpleNamespace(pk='template',title='舟山',current=SimpleNamespace(snapshot={'manifest':{'assetTable':manifest['assetTable'],'pages':[{'id':'namespace-kept','title':'保留页'}]}}))
            rows=collect(root,template,{})
            self.assertEqual(len(rows),1)
            self.assertEqual((rows[0]['type'],rows[0]['kind'],rows[0]['subcategory']),('background','background','paper_texture'))
            self.assertEqual(rows[0]['sources'][0]['page_id'],'namespace-kept')
            obj=json.loads((root/'kept.json').read_text());obj['layers'][0]['name']='�照片卡乱码'
            (root/'kept.json').write_text(json.dumps(obj))
            self.assertEqual(collect(root,template,{}),[])
            repaired=collect(root,template,{'kept':{'include':True,'name':'背景_纸张','kind':'background','subcategory':'paper_texture'}})
            self.assertEqual(repaired[0]['name'],'背景_纸张')

    def test_query_separator_is_not_a_route_component(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        client=APIClient();client.force_authenticate(get_user_model().objects.create_user(username='route-check'))
        self.assertEqual(client.get('/api/v1/materials/libraries/?type=sticker').status_code,200)
        self.assertEqual(client.get('/api/v1/materials/libraries/%3Ftype=sticker').status_code,404)
