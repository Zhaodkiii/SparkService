from billing.testing import legacy_free
import io
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from .models import *
from .services import revision


@override_settings(MIDDLEWARE=[], LOGGING={})
class CatalogTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='admin',is_staff=True,is_superuser=True)
        self.client=APIClient();self.client.force_authenticate(self.user)
        self.sign=patch('material_library.catalog_v2.sign',return_value='https://test.oss-cn-beijing.aliyuncs.com/image');self.sign.start();self.addCleanup(self.sign.stop)
        self.oldsign=patch('material_library.views.sign',return_value='https://test.oss-cn-beijing.aliyuncs.com/image');self.oldsign.start();self.addCleanup(self.oldsign.stop)
        self.blob=ResourceBlob.objects.create(sha256='c'*64,object_key='traveldiary/presets/blobs/sha256/'+'c'*64,byte_size=100,width=800,height=800,mime='image/png')
        material=Material.objects.create(source_identity='test:flower',material_type='sticker')
        self.r=revision(material,dict(name='白色花枝',kind='illustration',subcategory='botanical',keywords=['花草'],aliases=[],resource_id=self.blob.pk,thumbnail_id=self.blob.pk,sources=[]))
        response=self.client.post('/api/v1/materials/manage/libraries/',{'title':'春日','type':'sticker'},format='json')
        self.assertEqual(response.status_code,201,response.data)
        self.pk=response.data['id'];self.base=f'/api/v1/materials/manage/libraries/{self.pk}/'
        self.content=dict(title='春日',description='旅行装饰',tags=['旅行'],cover=self.blob.pk,previews=[self.blob.pk],items=[{'revision':self.r.pk}])
        response=self.client.patch(self.base+'draft/',{'expected_draft_revision':1,'content':self.content},format='json');self.assertEqual(response.status_code,200,response.data)
        self.publish={'expected_draft_revision':2,'expected_version':0,'idempotency_key':'first'}
        self.assertEqual(self.client.post(self.base+'publish/',self.publish,format='json').status_code,200)
        legacy_free('sticker_library',MaterialLibrary.objects.get(pk=self.pk))

    def test_admin_retains_withdrawn_cover_and_marks_draft_changes(self):
        lib=MaterialLibrary.objects.get(pk=self.pk)
        lib.active=False;lib.save()
        draft=LibraryDraft.objects.get(library=lib)
        draft.content={**draft.content,'title':'待发布名称'};draft.save()
        row=self.client.get('/api/v1/materials/manage/libraries/').data[0]
        self.assertEqual(row['publication_state'],'withdrawn')
        self.assertTrue(row['has_draft_changes'])
        self.assertFalse(row['gallery_visible'])
        self.assertIsNotNone(row['cover'])

    def test_admin_list_batches_page_queries_and_counts_only_current_members(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        lib=MaterialLibrary.objects.get(pk=self.pk)
        old=LibraryVersion.objects.create(library=lib,number=2,content=self.content)
        LibraryItem.objects.create(version=old,material=self.r.material,revision=self.r)
        # Historical membership must not inflate the current version count.
        for i in range(19):
            other=MaterialLibrary.objects.create(title=f'批量{i}',library_type='sticker')
            version=LibraryVersion.objects.create(library=other,number=1,content=self.content)
            LibraryItem.objects.create(version=version,material=self.r.material,revision=self.r)
            other.current=version;other.save()
        self.r.material.active=False;self.r.material.save()
        endpoint='/api/v1/materials/manage/libraries/'
        # Warm up DRF throttling/permission bookkeeping before measuring SQL.
        self.client.get(endpoint,{'paged':1,'page_size':1})
        with CaptureQueriesContext(connection) as queries:
            response=self.client.get(endpoint,{'paged':1,'page_size':20})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['total'],20)
        self.assertEqual(len(response.data['items']),20)
        for row in response.data['items']:
            self.assertEqual(row['count'],0)
            self.assertEqual(row['total_count'],1)
            self.assertIsNotNone(row['cover'])
        self.assertLessEqual(len(queries),5, [q['sql'] for q in queries])
        # The page fetch itself must not group the wide joined records.
        page_sql=next(q['sql'] for q in queries if 'LIMIT 20' in q['sql'])
        self.assertNotIn('GROUP BY',page_sql)

    def test_admin_list_uses_latest_source_sync_task_and_preserves_legacy_shape(self):
        import uuid
        for side,state in [('source','failed'),('source','ready'),('target','conflict')]:
            MaterialSyncTask.objects.create(side=side,source_environment='test',library_uuid=self.pk,
                source_version=1,content_hash='a'*64,state=state,idempotency_key=uuid.uuid4().hex)
        response=self.client.get('/api/v1/materials/manage/libraries/')
        self.assertIsInstance(response.data,list)
        self.assertEqual(response.data[0]['production_sync']['state'],'ready')
        self.assertEqual(response.data[0]['count'],1)

    def test_draft_offers_latest_revision_without_mutating_published_members(self):
        newest=revision(self.r.material,dict(name='新版花枝',kind='illustration',subcategory='botanical',keywords=[],aliases=[],resource_id=self.blob.pk,thumbnail_id=self.blob.pk,sources=[]))
        data=self.client.get(self.base+'draft/').data
        self.assertEqual(data['latest_items'][0]['revision'],newest.pk)
        self.assertEqual(data['content']['items'][0]['revision'],self.r.pk)
        self.assertEqual(LibraryItem.objects.get(version__library_id=self.pk).revision_id,self.r.pk)

    def test_independent_pack_and_legacy_compatibility(self):
        self.assertEqual(self.client.get('/api/v1/materials/libraries/').data,[])
        response=self.client.get('/api/v1/materials/libraries/?schema=2')
        self.assertEqual(response.status_code,200,response.data)
        self.assertIsNone(response.data['items'][0]['template_id'])
        self.assertEqual(response.data['items'][0]['count'],1)

    def test_admin_pagination_reaches_packs_beyond_legacy_limit(self):
        MaterialLibrary.objects.bulk_create([MaterialLibrary(title=f'包{i:04}',library_type='background') for i in range(501)])
        data=self.client.get('/api/v1/materials/manage/libraries/',{'paged':1,'page':6,'page_size':100,'type':'background','state':'draft'}).data
        self.assertEqual(data['total'],501)
        self.assertEqual(data['page'],6)
        self.assertEqual(len(data['items']),1)
        self.assertEqual(data['items'][0]['publication_state'],'draft')

    def test_material_search_matches_latest_revision_not_obsolete_name(self):
        newest=revision(self.r.material,dict(name='新名字',kind='illustration',subcategory='botanical',keywords=[],aliases=[],resource_id=self.blob.pk,thumbnail_id=self.blob.pk,sources=[]))
        old=self.client.get('/api/v1/materials/manage/materials/',{'paged':1,'q':'白色花枝'}).data
        current=self.client.get('/api/v1/materials/manage/materials/',{'paged':1,'q':'新名字'}).data
        self.assertEqual(old['total'],0)
        self.assertEqual(current['items'][0]['revision'],newest.pk)

    def test_template_picker_excludes_private_and_already_associated_type(self):
        from diary_presets.models import Series,Template
        series=Series.objects.create(slug='picker',title='城市')
        template=Template.objects.create(series=series,title='苏州')
        MaterialLibrary.objects.create(template=template,title='苏州贴纸',library_type='sticker')
        Template.objects.create(series=series,title='私人苏州',audience='private',owner=self.user,customization_id=__import__('uuid').uuid4())
        endpoint='/api/v1/materials/manage/templates/'
        self.assertEqual(self.client.get(endpoint,{'paged':1,'q':'苏州','type':'sticker'}).data['total'],0)
        data=self.client.get(endpoint,{'paged':1,'q':'苏州','type':'background'}).data
        self.assertEqual([row['id'] for row in data['items']],[str(template.pk)])

    def test_usage_reports_published_pack_and_fixed_template_revision(self):
        from diary_presets.models import Series,Template,Version
        series=Series.objects.create(slug='usage',title='城市')
        template=Template.objects.create(series=series,title='苏州')
        preset=Version.objects.create(template=template,number=1,snapshot={})
        lib=MaterialLibrary.objects.get(pk=self.pk)
        TemplateLibraryBinding.objects.create(preset_version=preset,library_type='sticker',library_version=lib.current)
        response=self.client.get(f'/api/v1/materials/manage/materials/{self.r.material_id}/usage/')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(len(response.data['items']),1)
        self.assertEqual(response.data['items'][0]['template_versions'],[1])
        self.assertEqual(response.data['items'][0]['revision'],self.r.pk)

    def test_publish_is_idempotent_and_conflicts_do_not_mutate(self):
        self.assertEqual(self.client.post(self.base+'publish/',self.publish,format='json').data['version'],1)
        self.assertEqual(self.client.post(self.base+'publish/',dict(self.publish,expected_version=1),format='json').status_code,409)
        self.assertEqual(self.client.patch(self.base+'draft/',{'expected_draft_revision':1,'content':self.content},format='json').status_code,409)
        self.assertEqual(LibraryVersion.objects.filter(library_id=self.pk).count(),1)

    def test_my_union_and_independent_favorites(self):
        self.assertEqual(self.client.get('/api/v1/materials/items/?schema=2&scope=my').data['items'],[])
        for target,pk in [('libraries',self.pk),('items',self.r.material_id)]:
            self.assertEqual(self.client.post(f'/api/v1/materials/{target}/{pk}/favorite/',{'favorite':True},format='json').status_code,200)
        response=self.client.get('/api/v1/materials/items/?schema=2&scope=my')
        self.assertEqual(len(response.data['items']),1)
        self.client.post(f'/api/v1/materials/libraries/{self.pk}/favorite/',{'favorite':False},format='json')
        self.assertEqual(len(self.client.get('/api/v1/materials/items/?schema=2&scope=my').data['items']),1)
        self.assertEqual(self.client.get('/api/v1/materials/items/?schema=2&scope=my&favorites=1').status_code,400)

    def test_downloading_is_json_and_takedown_revokes_new_plans(self):
        endpoint=f'/api/v1/materials/revisions/{self.r.pk}/download/?schema=2'
        response=self.client.post(endpoint,{'library_id':self.pk,'library_version':1},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertTrue(response.data['url'].startswith('https://test.oss-'))
        self.assertNotIn('data',response.data)
        lib=MaterialLibrary.objects.get(pk=self.pk)
        self.assertEqual(self.client.post(self.base+'availability/',{'expected_state_revision':lib.state_revision,'active':False},format='json').status_code,200)
        self.assertEqual(self.client.post(endpoint,{'library_id':self.pk,'library_version':1},format='json').status_code,400)

    def test_cursor_is_bound_to_account_and_filters(self):
        # Two rows allow a real continuation token.
        lib=MaterialLibrary.objects.get(pk=self.pk)
        other=MaterialLibrary.objects.create(title='第二包',library_type='sticker')
        other.current=LibraryVersion.objects.create(library=other,number=1,content=lib.current.content);other.save()
        response=self.client.get('/api/v1/materials/libraries/?schema=2&limit=1')
        cursor=response.data['next_cursor'];self.assertTrue(cursor)
        self.assertEqual(self.client.get('/api/v1/materials/libraries/',{'schema':2,'limit':1,'cursor':cursor}).status_code,200)
        self.assertEqual(self.client.get('/api/v1/materials/libraries/',{'schema':2,'limit':1,'q':'different','cursor':cursor}).status_code,400)

    def test_upload_gate_json_only_and_admin_permissions(self):
        self.assertEqual(self.client.post('/api/v1/materials/manage/uploads/',{},format='json').status_code,400)
        self.assertEqual(self.client.post('/api/v1/materials/manage/uploads/',{'file':io.BytesIO(b'fake')},format='multipart').status_code,415)
        self.user.is_superuser=False;self.user.is_staff=False;self.user.save()
        self.assertEqual(self.client.get(self.base+'draft/').status_code,403)

    def test_takedown_keeps_favorites_manageable(self):
        self.client.post(f'/api/v1/materials/items/{self.r.material_id}/favorite/',{'favorite':True},format='json')
        self.r.material.active=False;self.r.material.save()
        response=self.client.get('/api/v1/materials/items/?schema=2&favorites=1')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['items'][0]['availability'],'unavailable')
        self.assertEqual(response.data['items'][0]['thumbnail_url'],'')
        self.assertEqual(self.client.post(f'/api/v1/materials/items/{self.r.material_id}/favorite/',{'favorite':False},format='json').status_code,200)

    def test_snapshot_keeps_revision_when_pack_publishes_during_pagination(self):
        lib=MaterialLibrary.objects.get(pk=self.pk)
        materials=[]
        for index in range(3):
            material=Material.objects.create(source_identity=f'pagination:{index}',material_type='sticker')
            r=revision(material,dict(name=f'贴纸{index}',kind='illustration',subcategory='object',keywords=[],aliases=[],resource_id=self.blob.pk,thumbnail_id=self.blob.pk,sources=[]))
            LibraryItem.objects.create(version=lib.current,revision=r,material=material,position=index+1);materials.append(r)
        first=self.client.get('/api/v1/materials/items/?schema=2&limit=1')
        cursor=first.data['next_cursor']
        old_ids=set(lib.current.items.values_list('revision_id',flat=True))
        v=LibraryVersion.objects.create(library=lib,number=2,content=lib.current.content)
        LibraryItem.objects.create(version=v,revision=self.r,material=self.r.material,position=0)
        lib.current=v;lib.save()
        second=self.client.get('/api/v1/materials/items/',{'schema':'2','limit':1,'cursor':cursor})
        self.assertEqual(len(second.data['items']),1)
        self.assertIn(second.data['items'][0]['revision'],old_ids)

    def test_fixed_template_binding_is_not_overwritten_by_new_pack(self):
        from diary_presets.models import Series,Template,Version
        series=Series.objects.create(slug='binding',title='城市')
        template=Template.objects.create(series=series,title='苏州')
        preset=Version.objects.create(template=template,number=1,snapshot={})
        template.current=preset;template.save()
        lib=MaterialLibrary.objects.get(pk=self.pk);lib.template=template;lib.save()
        TemplateLibraryBinding.objects.create(preset_version=preset,library_type='sticker',library_version=lib.current)
        d=LibraryDraft.objects.get(library=lib)
        payload={'expected_draft_revision':d.revision,'expected_version':1,'idempotency_key':'second'}
        self.assertEqual(self.client.post(self.base+'publish/',payload,format='json').status_code,200)
        response=self.client.get('/api/v1/materials/libraries/',{'schema':2,'template':template.pk,'template_version':1})
        self.assertEqual(response.data['items'][0]['version'],1)
        response=self.client.get(f'/api/v1/materials/libraries/{lib.pk}/items/?schema=2&version=1')
        self.assertEqual(response.data['items'][0]['revision'],self.r.pk)

    def test_dictionary_disables_new_use_without_changing_old_revisions(self):
        result=self.client.post('/api/v1/materials/manage/categories/',{'kind':'illustration','subcategory':'botanical','title':'花草','active':False},format='json')
        self.assertEqual(result.status_code,200,result.data)
        result=self.client.post(self.base+'validate/',{'expected_draft_revision':3},format='json')
        self.assertEqual(result.status_code,400)
        self.assertEqual(self.client.get(f'/api/v1/materials/libraries/{self.pk}/items/?schema=2&version=1').status_code,200)

    def test_preview_resolution_rejects_unrelated_hash(self):
        response=self.client.post('/api/v1/materials/previews/resolve/',{'resources':[{'library_id':self.pk,'version':1,'resource_id':'d'*64}]},format='json')
        self.assertEqual(response.status_code,400)

    def test_json_body_limit_and_file_request_rejected_before_parser(self):
        from material_library.middleware import MaterialControlPlaneGuard
        from django.test import RequestFactory
        next_handler=MagicMock()
        middleware=MaterialControlPlaneGuard(next_handler)
        factory=RequestFactory()
        response=middleware(factory.post('/api/v1/materials/manage/uploads/',b'x'*262145,content_type='application/json'))
        self.assertEqual(response.status_code,413);next_handler.assert_not_called()
        response=middleware(factory.post('/api/v1/materials/manage/uploads/',b'fake',content_type='image/png'))
        self.assertEqual(response.status_code,415);next_handler.assert_not_called()

    def test_invalid_parameters_return_client_errors(self):
        for query in ['type=unknown','kind=unknown','favorites=yes','template_version=invalid']:
            path='/api/v1/materials/libraries/?schema=2&'+query if query.startswith('template') else '/api/v1/materials/items/?schema=2&'+query
            self.assertEqual(self.client.get(path).status_code,400,query)
        self.assertEqual(self.client.get(f'/api/v1/materials/libraries/{self.pk}/?version=no').status_code,400)
        self.assertEqual(self.client.post('/api/v1/materials/previews/resolve/',{'resources':[None]},format='json').status_code,400)

    def test_material_roles_do_not_grant_publish_permission(self):
        from django.contrib.auth.models import Permission
        operator=get_user_model().objects.create_user(username='catalog-editor')
        operator.user_permissions.add(Permission.objects.get(codename='change_materiallibrary'))
        self.client.force_authenticate(operator)
        response=self.client.patch(self.base+'draft/',{'expected_draft_revision':3,'content':self.content},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.client.post(self.base+'publish/',{'expected_draft_revision':4,'expected_version':1,'idempotency_key':'editor'},format='json').status_code,403)

    def test_search_ranks_exact_name_before_keyword_match(self):
        lib=MaterialLibrary.objects.get(pk=self.pk)
        m=Material.objects.create(source_identity='search:exact',material_type='sticker')
        r=revision(m,dict(name='花草',kind='illustration',subcategory='object',keywords=[],aliases=[],resource_id=self.blob.pk,thumbnail_id=self.blob.pk,sources=[]))
        LibraryItem.objects.create(version=lib.current,revision=r,material=m,position=1)
        response=self.client.get('/api/v1/materials/items/?schema=2&q=花草')
        self.assertEqual(response.data['items'][0]['id'],str(m.pk))
