from billing.testing import legacy_free
from copy import deepcopy
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Series, Template, Version, SearchTaxon, CatalogEntry
from .views import publish
from .reading_units import suggest, validate
from .domain import select
from .search import index_version


def fixture():
    ids=['cover','lion-left','lion-right','boat-left','boat-right']
    pages=[{'data':{'id':p,'title':p,'preview':{'thumbnailPath':p+'.jpg','largePath':p+'.jpg'}},'files':[p+'.json',p+'.jpg']} for p in ids]
    paths=[p+ext for p in ids for ext in ['.json','.jpg']]
    m={'format':'TravelDiary.PresetBook','schemaVersion':2,'packageVersion':1,'layerSchemaVersion':2,'templateBookID':'city-suzhou','title':'苏州园林合集','seriesID':'city','coverPageID':'cover',
       'pages':[{'id':p,'title':p,'path':p+'.json'} for p in ids], 'pageSize':{'width':100,'height':140},'objectTable':{},'assetTable':{},
       'requiredCapabilities':[],'files':[{'path':p,'sha256':'a'*64,'byteCount':1} for p in paths],
       'metadata':{'locationScope':'single_city','defaultLocationIDs':['loc-suzhou']},
       'pageMetadata':{p:{'contentRole':'front_cover' if p=='cover' else 'content','displayTitle':p} for p in ids},
       'readingUnits':[
        {'id':'cover-unit','kind':'cover','title':'园林狮子林封面','position':0,'leftPageID':None,'rightPageID':'cover','pairingSource':'explicit','searchEnabled':False},
        {'id':'lion','kind':'spread','title':'狮子林 · 园林漫游','position':1,'leftPageID':'lion-left','rightPageID':'lion-right','pairingSource':'explicit','searchEnabled':True,'locationMode':'explicit','locationIDs':['loc-shizilin'],'tagIDs':['theme-garden'],'searchKeywords':['假山漫游']},
        {'id':'boat','kind':'spread','title':'船过蓝调','position':2,'leftPageID':'boat-left','rightPageID':'boat-right','pairingSource':'explicit','searchEnabled':True,'locationMode':'inherit','locationIDs':[],'tagIDs':['theme-boat'],'searchKeywords':[]}
       ]}
    return {'manifest':m,'pages':pages,'keys':{p:'blob/'+p for p in paths}}


@patch('diary_presets.storage.sign',return_value='https://preview.test/image')
class SearchTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='reader')
        self.admin=get_user_model().objects.create_superuser(username='admin',password='test')
        self.series=Series.objects.create(slug='city',title='城市')
        for key,name,dim,parent,aliases in [('loc-suzhou','苏州','location',None,['蘇州','suzhou']),('loc-shizilin','狮子林','location','loc-suzhou',['獅子林']),('theme-garden','园林','theme',None,['園林']),('theme-boat','船游','theme',None,[])]:
            SearchTaxon.objects.create(id=key,name=name,dimension=dim,parent_id=parent,aliases=aliases)
        self.template=Template.objects.create(title='苏州园林合集',series=self.series,draft=fixture())
        publish(self.template,self.admin)
        legacy_free('template',self.template)
        self.client=APIClient();self.client.force_authenticate(self.user)
    def search(self,q='',**params):return self.client.get('/api/v1/diary-presets/search/',{'kind':'spread','q':q,**params})
    def test_city_theme_and_specific_place(self,_):
        for query,expected in [('苏州',{'lion','boat'}),('园林',{'lion'}),('狮子林',{'lion'}),('苏州 园林',{'lion'}),('苏州园林',{'lion'}),('蘇州園林',{'lion'}),('獅子林',{'lion'}),('苏州未知词',set()),('假山漫游',{'lion'})]:
            r=self.search(query);self.assertEqual(r.status_code,200,r.data);self.assertEqual({e['unit_id'] for e in r.data['entries']},expected,query)
    def test_cover_never_returned_and_no_parent_theme_inheritance(self,_):
        r=self.search();self.assertEqual(r.data['total'],2)
        self.assertEqual(self.search('园林').data['total'],1)
    def test_filters_combine_and_unknown_ids_rejected(self,_):
        self.assertEqual(self.search('苏州',theme_ids='theme-garden').data['total'],1)
        self.assertEqual(self.search('苏州',theme_ids='missing').status_code,400)
    def test_stale_cursor_and_query_binding(self,_):
        r=self.search(limit=1);cursor=r.data['next_cursor'];self.assertTrue(cursor)
        self.assertEqual(self.search(limit=1,cursor=cursor).data['total'],2)
        self.assertEqual(self.search('园林',limit=1,cursor=cursor).status_code,409)
        self.template.active=False;self.template.save(update_fields=['active'])
        self.assertEqual(self.search(limit=1,cursor=cursor).status_code,409)
        self.assertEqual(self.search().data['total'],0)
    def test_private_template_and_inactive_series_hidden(self,_):
        private=Template.objects.create(title='private',series=self.series,audience='private',owner=self.user,customization_id='11111111-1111-1111-1111-111111111111',draft=fixture())
        publish(private,self.admin)
        self.assertEqual(self.search().data['total'],2)
        self.series.active=False;self.series.save();self.assertEqual(self.search().data['total'],0)
    def test_plan_expands_server_unit_and_preserves_roles(self,_):
        url=f'/api/v1/diary-presets/templates/{self.template.id}/1/'
        r=self.client.post(url,{'selection':{'kind':'spread','unit_id':'lion'}},format='json')
        self.assertEqual(r.status_code,201,r.data)
        m=r.data['manifest'];self.assertEqual([p['id'] for p in m['pages']],['lion-left','lion-right'])
        self.assertEqual(m['coverPageID'],'lion-left');self.assertEqual(m['pageMetadata']['lion-left']['contentRole'],'content');validate(m)
        self.assertEqual(self.client.post(url,{'selection':{'kind':'spread','unit_id':'cover-unit'}},format='json').status_code,400)
        self.assertEqual(self.client.post(url,{'selection':{'kind':'spread','unit_id':'lion'},'page_ids':['cover']},format='json').status_code,400)
    def test_single_selection_has_no_dangling_spread(self,_):
        m=select(fixture(),['lion-right'])['manifest'];validate(m)
        self.assertEqual(m['readingUnits'][0]['kind'],'single');self.assertFalse(m['readingUnits'][0]['searchEnabled'])
    def test_invalid_pair_publish_rolls_back(self,_):
        before=Version.objects.count();self.template.draft['manifest']['readingUnits'][1]['rightPageID']='cover'
        with self.assertRaises(Exception):publish(self.template,self.admin)
        self.assertEqual(Version.objects.count(),before)
        self.assertEqual(self.search().data['total'],2)
    def test_old_versions_excluded_and_keyword_removal(self,_):
        self.template.draft['manifest']['readingUnits'][1]['searchKeywords']=[];publish(self.template,self.admin)
        self.assertEqual(self.search().data['total'],2);self.assertEqual(self.search('假山漫游').data['total'],0)
    def test_metadata_is_admin_only_and_revision_checked(self,_):
        url=f'/api/admin/v1/diary-presets/templates/{self.template.id}/reading-units/'
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_authenticate(self.admin)
        m=deepcopy(self.template.draft['manifest']);m['readingUnits'][1]['searchKeywords']=['新词']
        self.assertEqual(self.client.put(url,dict(revision=0,readingUnits=m['readingUnits']),format='json').status_code,409)
        r=self.client.put(url,dict(revision=self.template.revision,readingUnits=m['readingUnits']),format='json');self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(self.search('新词').data['total'],0)
        trial=self.client.post(f'/api/admin/v1/diary-presets/templates/{self.template.id}/search-preview/',{'revision':r.data['revision'],'kind':'spread','q':'新词'},format='json')
        self.assertEqual(trial.status_code,200,trial.data);self.assertEqual(trial.data['total'],1)
    def test_alias_cycle_and_duplicate_validation(self,_):
        self.client.force_authenticate(self.admin)
        r=self.client.patch('/api/admin/v1/diary-presets/tags/loc-suzhou/',{'parent':'loc-shizilin'},format='json');self.assertEqual(r.status_code,400)
        r=self.client.post('/api/admin/v1/diary-presets/tags/',{'id':'duplicate','dimension':'theme','name':'新主题','aliases':['園林']},format='json');self.assertEqual(r.status_code,400)
    def test_rebuild_is_idempotent(self,_):
        index_version(self.template,self.template.current);index_version(self.template,self.template.current)
        self.assertEqual(CatalogEntry.objects.filter(version=self.template.current).count(),3)
    def test_query_limits_and_literal_special_chars(self,_):
        self.assertEqual(self.search('x'*101).status_code,400)
        self.assertEqual(self.search(limit=61).status_code,400)
        self.assertEqual(self.search('%_').data['total'],0)
    def test_unconfirmed_or_noncontent_spread_rejected(self,_):
        for change in ['unconfirmed','cover','missing']:
            m=fixture()['manifest']
            if change=='unconfirmed':m['readingUnits'][1]['pairingSource']='suggested'
            elif change=='cover':m['pageMetadata']['lion-left']['contentRole']='front_cover'
            else:m['readingUnits'][1]['rightPageID']=None
            with self.assertRaises(ValueError):validate(m)
    def test_v1_catalog_keeps_compatibility(self,_):
        self.assertEqual(self.client.get('/api/v1/diary-presets/catalog/').data['books'],[])
        self.assertEqual(len(self.client.get('/api/v1/diary-presets/catalog/',{'schema_max':2}).data['books']),1)
    def test_suggestions_do_not_confirm_pairs(self,_):
        m=fixture()['manifest'];m.pop('readingUnits');m['pages'][1]['title']='狮子林-左页';m['pages'][2]['title']='狮子林-右页'
        m=suggest(m);validate(m)
        self.assertTrue(all(not u['searchEnabled'] and u['pairingSource']=='suggested' for u in m['readingUnits']))
    def test_reupload_keeps_confirmed_keywords_and_changed_pixels_require_review(self,_):
        from .reading_units import retain_confirmed_metadata
        previous=fixture();incoming=fixture()
        incoming['manifest']['readingUnits'][1]['searchKeywords']=['上传包里的候选词']
        merged=retain_confirmed_metadata(previous,incoming)
        self.assertEqual(merged['manifest']['readingUnits'][1]['searchKeywords'],['假山漫游'])
        incoming['keys']['lion-left.jpg']='blob/new-image'
        changed=retain_confirmed_metadata(previous,incoming)
        self.assertFalse(changed['manifest']['readingUnits'][1]['searchEnabled'])
        self.assertTrue(changed['manifest']['readingUnits'][1]['requiresReview'])
    def test_interleaved_reorder_splits_pairs_instead_of_reassigning(self,_):
        part=select(fixture(),['cover','lion-left','boat-left','lion-right','boat-right'])
        validate(part['manifest'])
        self.assertTrue(all(u['kind']!='spread' for u in part['manifest']['readingUnits']))
    def test_tag_merge_redirects_aliases_and_filters_without_rewriting_snapshot(self,_):
        old=deepcopy(self.template.current.snapshot)
        self.client.force_authenticate(self.admin)
        SearchTaxon.objects.create(id='classical-garden',dimension='theme',name='古典园林')
        r=self.client.post('/api/admin/v1/diary-presets/tags/theme-garden/merge/',{'target_id':'classical-garden'},format='json')
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(self.search('園林').data['total'],1)
        self.assertEqual(self.search(theme_ids='classical-garden').data['total'],1)
        self.assertEqual(self.search(theme_ids='theme-garden').data['total'],1)
        self.template.current.refresh_from_db();self.assertEqual(self.template.current.snapshot,old)
    def test_search_reads_projections_not_content_snapshots(self,_):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as queries:
            response=self.search('苏州')
        self.assertEqual(response.data['total'],2)
        self.assertTrue(all('"snapshot"' not in q['sql'] and '"draft"' not in q['sql'] for q in queries))
    def test_individual_metadata_patch_keeps_unprovided_fields(self,_):
        self.client.force_authenticate(self.admin)
        url=f'/api/admin/v1/diary-presets/templates/{self.template.id}/reading-units/lion/search-metadata/'
        response=self.client.patch(url,{'revision':self.template.revision,'search_keywords':[]},format='json')
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data['unit']['tagIDs'],['theme-garden'])
        self.assertEqual(response.data['unit']['searchKeywords'],[])
        self.assertEqual(response.data['published']['searchKeywords'],['假山漫游'])
