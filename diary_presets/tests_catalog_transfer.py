from copy import deepcopy
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from diary_presets.models import Series, Template, Version, Event, CatalogEntry, CatalogEntryTerm, SearchTaxon, Upload
from material_library.models import ResourceBlob, Material, MaterialRevision, MaterialLibrary, LibraryVersion, LibraryItem, LibraryFavorite
from print_orders.models import Product, Order
from scripts.preset_catalog_transfer import export_catalog, replace_catalog, validate_payload, resources


class CatalogTransferTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='catalog-test')
        self.series = Series.objects.create(slug='city', title='城市漫游')
        self.template = Template.objects.create(series=self.series, title='上海', draft={})
        snapshot = {'keys': {'cover.webp': 'traveldiary/presets/blobs/sha256/' + 'a' * 64},
                    'manifest': {'files': [{'path': 'cover.webp', 'byteCount': 123}], 'pages': [{'id': 'page-one'}]}}
        self.version = Version.objects.create(template=self.template, number=3, snapshot=snapshot, actor=self.user)
        self.template.current = self.version
        self.template.draft = snapshot
        self.template.save()
        Event.objects.create(template=self.template, actor=self.user, action='source-publish', detail={'source_sha256': 'abc'})
        self.taxon = SearchTaxon.objects.create(id='location:shanghai', dimension='location', name='上海')
        self.entry = CatalogEntry.objects.create(version=self.version, entity_type='book', entity_id='book', document={'version': 3})
        CatalogEntryTerm.objects.create(entry=self.entry, taxon=self.taxon, dimension='location')
        self.blob = ResourceBlob.objects.create(sha256='a' * 64, object_key=snapshot['keys']['cover.webp'], byte_size=123, width=10, height=10, mime='image/webp')
        self.material = Material.objects.create(source_identity='stable-sticker', material_type='sticker')
        self.revision = MaterialRevision.objects.create(material=self.material, digest='b' * 64, name='贴纸', kind='art', subcategory='city', resource=self.blob, thumbnail=self.blob)
        self.library = MaterialLibrary.objects.create(template=self.template, library_type='sticker', title='上海贴纸')
        library_version = LibraryVersion.objects.create(library=self.library, number=2, preset_version=self.version)
        self.library.current = library_version
        self.library.save()
        LibraryItem.objects.create(version=library_version, revision=self.revision, material=self.material)
        for title, width, height in [('A5', 148, 210), ('B5（ISO）', 176, 250)]:
            Product.objects.create(title=title, width_mm=width, height_mm=height, paper='250克双胶纸', binding='活页',
                                   active=True, proof_approved=True, proof_note='实物打样通过', proof_at=timezone.now(), proof_by='用户确认',
                                   regions=['上海市'], lead_time='制作周期：3天', terms='签收后7日内反馈', free_printing=True, max_pages=20, max_quantity=1)
        self.payload = export_catalog()

    def test_complete_public_graph_and_no_local_users(self):
        records = self.payload['records']
        self.assertTrue(any(record['model'] == 'material_library.libraryitem' for record in records))
        self.assertTrue(any(record['model'] == 'diary_presets.catalogentryterm' for record in records))
        self.assertTrue(all(record['fields'].get('actor') is None for record in records))
        self.assertEqual(list(resources(self.payload).values()), [123])

    def test_replaces_stale_public_preserves_private_and_favorites(self):
        private = Template.objects.create(series=self.series, title='私人', audience='private', owner=self.user, customization_id=uuid.uuid4())
        private_version = Version.objects.create(template=private, number=1, snapshot={})
        private.current = private_version
        private.save()
        stale = Template.objects.create(series=self.series, title='服务器旧目录')
        favorite = LibraryFavorite.objects.create(user=self.user, library=self.library)
        favorite_time = favorite.created_at
        old_version_id = self.version.pk
        self.template.title = '服务器改名'
        self.template.save()
        result = replace_catalog(self.payload)
        self.assertFalse(Template.objects.filter(pk=stale.pk).exists())
        self.template.refresh_from_db()
        private.refresh_from_db()
        self.assertEqual(self.template.title, '上海')
        self.assertEqual(self.template.current.number, 3)
        self.assertNotEqual(self.template.current_id, old_version_id)
        self.assertEqual(private.current_id, private_version.pk)
        self.assertTrue(LibraryFavorite.objects.filter(user=self.user, library_id=self.library.pk).exists())
        favorite.refresh_from_db()
        self.assertEqual(favorite.created_at, favorite_time)
        self.assertEqual(LibraryItem.objects.get(version__library_id=self.library.pk).version.preset_version_id, self.template.current_id)
        self.assertGreater(result['search_revision'], self.payload['search_revision'])

    def test_repeat_import_does_not_accumulate_records(self):
        replace_catalog(self.payload)
        counts = (Template.objects.count(), Version.objects.count(), MaterialRevision.objects.count(), Product.objects.count())
        replace_catalog(self.payload)
        self.assertEqual(counts, (Template.objects.count(), Version.objects.count(), MaterialRevision.objects.count(), Product.objects.count()))

    def test_numeric_item_order_survives_shuffled_package(self):
        LibraryItem.objects.all().delete()
        material = Material.objects.create(source_identity='second-sticker', material_type='sticker')
        revision = MaterialRevision.objects.create(material=material, digest='c' * 64, name='第二张', kind='art', subcategory='city', resource=self.blob, thumbnail=self.blob)
        LibraryItem.objects.create(pk=9, version=self.library.current, revision=self.revision, material=self.material, position=0)
        LibraryItem.objects.create(pk=10, version=self.library.current, revision=revision, material=material, position=1)
        payload = export_catalog()
        payload['records'].reverse()
        replace_catalog(payload)
        self.assertEqual(list(LibraryItem.objects.order_by('id').values_list('position', flat=True)), [0, 1])

    def test_failure_rolls_back_deletion_and_insertion(self):
        with patch('scripts.preset_catalog_transfer.verify_import', side_effect=ValueError('模拟核对失败')):
            with self.assertRaises(ValueError):
                replace_catalog(self.payload)
        self.template.refresh_from_db()
        self.assertEqual(self.template.current_id, self.version.pk)
        self.assertEqual(Version.objects.count(), 1)

    def test_rejects_incomplete_graph_and_empty_source(self):
        payload = deepcopy(self.payload)
        payload['records'] = [record for record in payload['records'] if record['model'] != 'diary_presets.version']
        with self.assertRaises(ValueError):
            validate_payload(payload)
        payload['records'] = []
        with self.assertRaises(ValueError):
            validate_payload(payload)

    def test_pending_upload_blocks_before_deletion(self):
        Upload.objects.create(template=self.template, actor=self.user, revision=1, object_key='pending', size=10)
        with self.assertRaises(ValueError):
            replace_catalog(self.payload)
        self.assertTrue(Template.objects.filter(pk=self.template.pk).exists())

    def test_print_settings_preserve_server_product_uuid_and_order_snapshots(self):
        source_product = Product.objects.get(title='A5')
        source_product.delete()
        server_product = Product.objects.create(title='A5', width_mm=148, height_mm=210, paper='旧纸张', binding='旧装订', revision=100)
        order = Order.objects.create(owner=self.user, product=server_product, creation_key=uuid.uuid4(), request_hash='c' * 64,
                                     title='已有订单', spec={'paper': '订单旧纸张'}, address={}, snapshot={}, quantity=1, page_count=2, total_fen=0)
        replace_catalog(self.payload)
        server_product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order.product_id, server_product.pk)
        self.assertEqual(order.spec, {'paper': '订单旧纸张'})
        self.assertEqual(server_product.paper, '250克双胶纸')
        self.assertTrue(server_product.active)
        self.assertEqual(server_product.max_pages, 20)
        self.assertGreater(server_product.revision, 100)
        self.assertEqual(Product.objects.filter(width_mm=148, height_mm=210).count(), 1)

    def test_rejects_unproven_active_print_product(self):
        payload = deepcopy(self.payload)
        product = next(record for record in payload['records'] if record['model'] == 'print_orders.product')
        product['fields']['proof_note'] = ''
        with self.assertRaises(ValueError):
            validate_payload(payload)

    def test_uuid_collision_with_private_template_is_blocked(self):
        self.template.audience = 'private'
        self.template.owner = self.user
        self.template.customization_id = uuid.uuid4()
        self.template.save()
        with self.assertRaises(ValueError):
            replace_catalog(self.payload)

    def test_private_content_is_not_exported(self):
        private = Template.objects.create(series=self.series, title='私人', audience='private', owner=self.user, customization_id=uuid.uuid4())
        Version.objects.create(template=private, number=1, snapshot={})
        payload = export_catalog()
        self.assertFalse(any(str(record['pk']) == str(private.pk) for record in payload['records']))
        self.assertEqual(sum(record['model'] == 'diary_presets.version' for record in payload['records']), 1)

    def test_all_historical_versions_are_preserved(self):
        Version.objects.create(template=self.template, number=1, snapshot={})
        payload = export_catalog()
        replace_catalog(payload)
        self.assertEqual(set(Version.objects.filter(template_id=self.template.pk).values_list('number', flat=True)), {1, 3})

    def test_unrelated_server_spec_with_orders_is_disabled_and_preserved(self):
        obsolete = Product.objects.create(title='旧规格', width_mm=200, height_mm=300, paper='纸', binding='装订', active=True)
        order = Order.objects.create(owner=self.user, product=obsolete, creation_key=uuid.uuid4(), request_hash='d' * 64,
                                     title='旧规格订单', spec={}, address={}, snapshot={}, quantity=1, page_count=2, total_fen=0)
        replace_catalog(self.payload)
        obsolete.refresh_from_db()
        self.assertFalse(obsolete.active)
        self.assertTrue(Order.objects.filter(pk=order.pk, product=obsolete).exists())

    def test_server_only_material_is_removed_but_private_shared_material_survives(self):
        private = Template.objects.create(series=self.series, title='私人', audience='private', owner=self.user, customization_id=uuid.uuid4())
        version = Version.objects.create(template=private, number=1, snapshot={})
        library = MaterialLibrary.objects.create(template=private, library_type='sticker', title='私人贴纸')
        library_version = LibraryVersion.objects.create(library=library, number=1, preset_version=version)
        for identity, shared in [('obsolete', False), ('private-shared', True)]:
            material = Material.objects.create(source_identity=identity, material_type='sticker')
            revision = MaterialRevision.objects.create(material=material, digest=identity, name=identity, kind='art', subcategory='city', resource=self.blob, thumbnail=self.blob)
            LibraryItem.objects.create(version=self.library.current, revision=revision, material=material)
            if shared:
                LibraryItem.objects.create(version=library_version, revision=revision, material=material)
        replace_catalog(self.payload)
        self.assertFalse(Material.objects.filter(source_identity='obsolete').exists())
        self.assertTrue(Material.objects.filter(source_identity='private-shared').exists())
        self.assertEqual(LibraryItem.objects.filter(version=library_version).count(), 1)
