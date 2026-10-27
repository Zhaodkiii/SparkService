from copy import deepcopy
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Series, Template, Version, PresetImportEvent, PresetImportItem
from .import_statistics import template_statistics, page_statistics


class ImportStatisticsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='statistics-reader')
        self.series = Series.objects.create(slug='stats', title='Stats')
        self.template = Template.objects.create(series=self.series, title='17 pages')
        self.version = Version.objects.create(template=self.template, number=1, snapshot={
            'manifest': {'pages': [{'id': str(i)} for i in range(17)]},
            'pages': [{'data': {'id': str(i), 'title': f'Page {i}'}} for i in range(17)]})
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = '/api/v1/diary-presets/import-events/'

    def payload(self, mode='book', ids=None):
        result = dict(operation_id=str(uuid4()), template_id=str(self.template.pk), version=1,
                      mode=mode, target_book_id=str(uuid4()), completed_at='2026-10-27T10:30:00+08:00')
        if ids is not None:
            result['pages'] = [dict(source_page_id=i, target_page_id=str(uuid4())) for i in ids]
        return result

    def post(self, data):
        return self.client.post(self.url, data, format='json')

    def test_book_then_page_are_independent(self):
        self.assertEqual(self.post(self.payload()).status_code, 201)
        self.assertEqual(PresetImportItem.objects.count(), 0)
        self.assertEqual(page_statistics(self.template), {})
        self.assertEqual(self.post(self.payload('selection', ['3'])).status_code, 201)
        self.assertEqual(template_statistics([self.template.pk])[str(self.template.pk)],
                         dict(book_count=1, selection_count=1, selected_page_count=1, user_count=1))
        self.assertEqual(page_statistics(self.template), {'3': 1})

    def test_selection_all_pages_is_not_book(self):
        self.assertEqual(self.post(self.payload('selection', list(map(str, range(17))))).status_code, 201)
        stats = template_statistics([self.template.pk])[str(self.template.pk)]
        self.assertEqual((stats['book_count'], stats['selection_count'], stats['selected_page_count']), (0, 1, 17))

    def test_replay_order_and_conflict(self):
        data = self.payload('selection', ['1', '2'])
        self.assertEqual(self.post(data).status_code, 201)
        data['pages'].reverse()
        for _ in range(10):
            response = self.post(data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data['duplicate'])
        data['target_book_id'] = str(uuid4())
        self.assertEqual(self.post(data).status_code, 409)
        self.assertEqual(PresetImportEvent.objects.count(), 1)
        self.assertEqual(PresetImportItem.objects.count(), 2)

    def test_invalid_payloads_leave_no_records(self):
        payloads = [self.payload('book', []), self.payload('book', ['1']),
                    self.payload('selection'), self.payload('selection', []),
                    self.payload('selection', ['missing']), self.payload('selection', ['1', '1'])]
        for payload in payloads:
            self.assertEqual(self.post(payload).status_code, 400)
        self.assertFalse(PresetImportEvent.objects.exists())

    def test_old_archived_version_and_duplicate(self):
        data = self.payload()
        self.template.active = False
        self.template.save()
        Version.objects.create(template=self.template, number=2, snapshot=self.version.snapshot)
        self.assertEqual(self.post(data).status_code, 201)
        self.assertEqual(self.post(data).status_code, 200)

    def test_private_other_owner_and_account_switch(self):
        other = get_user_model().objects.create_user(username='other')
        self.template.audience = 'private'; self.template.owner = other; self.template.customization_id = uuid4()
        self.template.save()
        self.assertEqual(self.post(self.payload()).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload(), format='json',
            HTTP_X_PRESET_IMPORT_OWNER=str(other.pk)).status_code, 403)
        self.assertFalse(PresetImportEvent.objects.exists())

    def test_authentication_and_admin_boundaries(self):
        self.client.force_authenticate(None)
        self.assertIn(self.post(self.payload()).status_code, (401, 403))
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get('/api/admin/v1/diary-presets/templates/').status_code, 403)

    def test_historical_pages_and_batch_summary(self):
        self.post(self.payload('selection', ['2']))
        self.post(self.payload())
        self.user.is_superuser=True; self.user.is_staff=True; self.user.save()
        response=self.client.get('/api/admin/v1/diary-presets/templates/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data[0]['import_statistics']['book_count'],1)
        response=self.client.get(f'/api/admin/v1/diary-presets/templates/{self.template.pk}/page-statistics/')
        self.assertEqual(response.status_code,200)
        page=next(p for p in response.data['pages'] if p['id']=='2')
        self.assertEqual(page['count'],1)
        self.assertTrue(page['removed'])
        self.assertEqual(self.client.get(f'/api/admin/v1/diary-presets/templates/{self.template.pk}/page-statistics/?version=bad').status_code,400)


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, connections
from django.test import TransactionTestCase


@skipUnless(connection.vendor == 'mysql', 'Concurrent commit test requires MySQL')
class ConcurrentImportStatisticsTests(TransactionTestCase):
    def test_ten_concurrent_replays_commit_once(self):
        user = get_user_model().objects.create_user(username='concurrent-statistics')
        series = Series.objects.create(slug='concurrent-statistics', title='test')
        template = Template.objects.create(series=series, title='test')
        Version.objects.create(template=template, number=1, snapshot={'manifest': {'pages': [{'id': 'page'}]}})
        payload = dict(operation_id=str(uuid4()), template_id=str(template.pk), version=1, mode='selection',
            target_book_id=str(uuid4()), completed_at='2026-10-27T10:30:00+08:00',
            pages=[dict(source_page_id='page', target_page_id=str(uuid4()))])
        barrier = Barrier(10)
        def submit(_):
            try:
                client = APIClient(); client.force_authenticate(get_user_model().objects.get(pk=user.pk))
                barrier.wait(timeout=10)
                return client.post('/api/v1/diary-presets/import-events/', payload, format='json').status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses = list(pool.map(submit, range(10)))
        self.assertEqual(statuses.count(201), 1)
        self.assertEqual(statuses.count(200), 9)
        self.assertEqual(PresetImportEvent.objects.count(), 1)
        self.assertEqual(PresetImportItem.objects.count(), 1)
