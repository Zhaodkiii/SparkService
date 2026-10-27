from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Series, Template
from .views import publish
from .reading_units import suggest


def snapshot():
    manifest = suggest(dict(format='TravelDiary.PresetBook', schemaVersion=1, layerSchemaVersion=2,
        templateBookID='fixture', packageVersion=1, title='纪念', seriesID='romance',
        pageSize=dict(width=100, height=140), coverPageID='cover',
        pages=[dict(id='cover', title='封面', path='cover.json')], files=[], objectTable={}, assetTable={}, requiredCapabilities=[]))
    return dict(manifest=manifest, keys={'cover.jpg': 'blob/cover'}, pages=[dict(data=dict(id='cover', title='封面', preview=dict(thumbnailPath='cover.jpg', largePath='cover.jpg')), files=[])])


@patch('diary_presets.storage.sign', return_value='https://example.test/preview.jpg')
class AlbumCatalogTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='album-reader')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        series = Series.objects.create(slug='romance', title='爱情纪念')
        self.journal = Template.objects.create(series=series, title='手帐', draft=snapshot())
        self.album = Template.objects.create(series=series, title='相册', content_kind='album', draft=snapshot())
        for template in [self.journal, self.album]:
            publish(template, None)

    def test_catalog_legacy_and_explicit_scopes(self, _):
        url = '/api/v1/diary-presets/catalog/'
        for scope, expected in [(None, [self.journal]), ('journal', [self.journal]), ('album', [self.album]), ('all', [self.journal, self.album])]:
            params = {'schema_max': 2}
            if scope: params['content_kind'] = scope
            response = self.client.get(url, params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual({b['id'] for b in response.data['books']}, {str(t.pk) for t in expected})
        self.assertEqual(self.client.get(url, {'content_kind': 'unknown'}).status_code, 400)

    def test_search_scopes_and_pinned_manifest(self, _):
        url = '/api/v1/diary-presets/search/'
        for scope, expected in [('journal', self.journal), ('album', self.album)]:
            response = self.client.get(url, {'kind': 'book', 'content_kind': scope})
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual([e['template_id'] for e in response.data['entries']], [str(expected.pk)])
            self.assertEqual(response.data['entries'][0]['content_kind'], scope)
            self.assertEqual(expected.current.snapshot['manifest']['contentKind'], scope)
        self.assertEqual(self.client.get(url, {'kind': 'book', 'content_kind': 'unknown'}).status_code, 400)
