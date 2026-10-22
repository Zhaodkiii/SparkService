"""Export and atomically replace the public preset catalog, including its libraries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

from django.apps import apps
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction


LABELS = (
    'diary_presets.series', 'diary_presets.searchtaxon',
    'diary_presets.template', 'diary_presets.version',
    'diary_presets.catalogentry', 'diary_presets.catalogentryterm',
    'material_library.resourceblob', 'material_library.material',
    'material_library.materialrevision', 'material_library.materiallibrary',
    'material_library.libraryversion', 'material_library.libraryitem',
    'diary_presets.event',
    'print_orders.product',
)
DEFERRED = {
    'diary_presets.searchtaxon': ('parent', 'merged_into'),
    'diary_presets.template': ('current',),
    'material_library.materiallibrary': ('current',),
}
SHARED = {
    'diary_presets.series': 'slug', 'diary_presets.searchtaxon': 'pk',
    'material_library.resourceblob': 'pk', 'material_library.material': 'pk',
}


def model(label):
    return apps.get_model(label)


def canonical(value):
    return json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def checksum(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def schema():
    return {label: [(field.name, field.get_internal_type(), field.null,
                     field.remote_field.model._meta.label_lower if field.remote_field else None)
                    for field in model(label)._meta.fields] for label in LABELS}


def oss_location():
    from django.conf import settings
    from diary_presets.storage import prefix
    return dict(bucket=settings.ALIYUN_OSS_BUCKET,
                endpoint=settings.ALIYUN_OSS_ENDPOINT.rstrip('/'), prefix=prefix())


def dump_rows(queryset):
    return serializers.serialize('python', sorted(queryset.order_by(), key=lambda instance: instance.pk))


def export_catalog():
    from diary_presets.models import Template, Version, CatalogEntry
    from material_library.models import MaterialLibrary, LibraryVersion, LibraryItem, MaterialRevision
    if connection.vendor == 'mysql' and not connection.in_atomic_block:
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
    with transaction.atomic():
        templates = Template.objects.filter(audience='public')
        versions = Version.objects.filter(template__in=templates)
        entries = CatalogEntry.objects.filter(version__in=versions)
        libraries = MaterialLibrary.objects.filter(template__in=templates)
        library_versions = LibraryVersion.objects.filter(library__in=libraries)
        items = LibraryItem.objects.filter(version__in=library_versions)
        materials = model('material_library.material').objects.filter(pk__in=items.values('material_id'))
        revisions = MaterialRevision.objects.filter(material__in=materials)
        from django.db.models import Q
        blobs = model('material_library.resourceblob').objects.filter(
            Q(pk__in=revisions.values('resource_id')) | Q(pk__in=revisions.values('thumbnail_id')))
        scopes = {
            'diary_presets.template': templates, 'diary_presets.version': versions,
            'diary_presets.catalogentry': entries,
            'diary_presets.catalogentryterm': model('diary_presets.catalogentryterm').objects.filter(entry__in=entries),
            'material_library.materiallibrary': libraries,
            'material_library.libraryversion': library_versions,
            'material_library.libraryitem': items,
            'material_library.material': materials,
            'material_library.materialrevision': revisions,
            'material_library.resourceblob': blobs,
            'diary_presets.event': model('diary_presets.event').objects.filter(template__in=templates),
        }
        records = []
        for label in LABELS:
            for record in dump_rows(scopes.get(label, model(label).objects.all())):
                if 'actor' in record['fields']:
                    record['fields']['actor'] = None
                records.append(record)
        state = model('diary_presets.searchstate').objects.filter(pk=1).first()
        payload = dict(format=1, scope='public-presets', schema=schema(), oss=oss_location(),
                       search_revision=state.revision if state else 1, records=records)
        payload = json.loads(canonical(payload))
        validate_payload(payload)
        return payload


def validate_payload(payload):
    if payload.get('format') != 1 or payload.get('scope') != 'public-presets':
        raise ValueError('不支持的数据包格式或范围')
    if canonical(payload.get('schema')) != canonical(schema()):
        raise ValueError('本地与服务器模型不同，请先发版和迁移')
    indexed = {label: {} for label in LABELS}
    for record in payload['records']:
        label = record['model']
        if label not in indexed or str(record['pk']) in indexed[label]:
            raise ValueError('非法模型或重复主键')
        expected = {field.name for field in model(label)._meta.fields if not field.primary_key}
        if set(record['fields']) != expected:
            raise ValueError('数据字段不完整：' + label)
        indexed[label][str(record['pk'])] = record
    if not indexed['diary_presets.template'] or not indexed['diary_presets.series']:
        raise ValueError('拒绝使用空目录清除服务器')
    sizes = set()
    for label, records in indexed.items():
        for record in records.values():
            fields = record['fields']
            if label == 'print_orders.product':
                size = (fields['width_mm'], fields['height_mm'])
                if size in sizes:
                    raise ValueError('本地印刷规格尺寸重复')
                sizes.add(size)
                if fields['active'] and not (
                    fields['proof_approved'] and fields['proof_note'].strip()
                    and fields['proof_at'] and fields['proof_by'].strip()
                    and fields['paper'].strip() and fields['binding'].strip()
                    and fields['regions'] and fields['lead_time'].strip() and fields['terms'].strip()
                    and fields['min_pages'] <= fields['max_pages'] and fields['max_quantity'] > 0
                    and (fields['free_printing'] or fields['base_fen'] + fields['page_fen'] > 0)
                    and fields['cover_mode'] == 'optional_shell'
                ):
                    raise ValueError('本地印刷规格开放条件不完整：' + fields['title'])
            for field in model(label)._meta.fields:
                if not field.remote_field:
                    continue
                value = fields[field.name]
                related = field.remote_field.model._meta.label_lower
                if value is None and not field.null:
                    raise ValueError('必填关联为空：' + label + '.' + field.name)
                if value is not None and (related not in indexed or str(value) not in indexed[related]):
                    raise ValueError('数据包缺少关联：' + label + '.' + field.name)
            if label == 'diary_presets.template':
                if fields['audience'] != 'public' or fields['owner'] is not None or fields['customization_id'] is not None:
                    raise ValueError('数据包包含私人定制')
                if fields['current'] is not None:
                    current = indexed['diary_presets.version'][str(fields['current'])]
                    if str(current['fields']['template']) != str(record['pk']):
                        raise ValueError('手帐当前版本不属于该手帐')
            if label == 'material_library.libraryversion':
                library = indexed['material_library.materiallibrary'][str(fields['library'])]
                version = indexed['diary_presets.version'][str(fields['preset_version'])]
                if str(library['fields']['template']) != str(version['fields']['template']):
                    raise ValueError('素材库版本与手帐不匹配')
            if label == 'material_library.materiallibrary' and fields['current'] is not None:
                current = indexed['material_library.libraryversion'][str(fields['current'])]
                if str(current['fields']['library']) != str(record['pk']):
                    raise ValueError('素材库当前版本不属于该库')
            if label == 'material_library.libraryitem':
                revision = indexed['material_library.materialrevision'][str(fields['revision'])]
                if str(revision['fields']['material']) != str(fields['material']):
                    raise ValueError('素材条目与修订不匹配')
    if not {(148, 210), (176, 250)} <= sizes:
        raise ValueError('本地配置缺少标准 A5 或 ISO B5')
    return indexed


def resources(payload):
    expected = {}
    prefix = payload['oss']['prefix'] + 'blobs/'

    def add(key, size=None):
        if not isinstance(key, str) or not key.startswith(prefix) or '?' in key or '..' in key.split('/'):
            raise ValueError('数据包含非公开预设 OSS 对象')
        if key in expected and size is not None and expected[key] not in (None, size):
            raise ValueError('同一 OSS 对象声明了不同大小')
        expected[key] = size if size is not None else expected.get(key)

    def snapshot(value):
        if not value:
            return
        keys = value.get('keys', {})
        for key in keys.values():
            add(key)
        for file in value.get('manifest', {}).get('files', []):
            add(keys[file['path']], file['byteCount'])

    for record in payload['records']:
        fields = record['fields']
        if record['model'] == 'diary_presets.version':
            snapshot(fields['snapshot'])
        elif record['model'] == 'diary_presets.template':
            snapshot(fields['draft'])
        elif record['model'] == 'material_library.resourceblob':
            add(fields['object_key'], fields['byte_size'])
    return expected


def check_oss(payload):
    from diary_presets.storage import bucket
    if payload['oss'] != oss_location():
        raise ValueError('服务器与本地 OSS 桶、端点或前缀不同，停止导入')
    objects = resources(payload)

    def head(item):
        key, size = item
        try:
            result = bucket().head_object(key)
        except Exception as error:
            raise ValueError('OSS 对象校验失败：' + key + '（' + type(error).__name__ + '）') from None
        if size is not None and result.content_length != size:
            raise ValueError('OSS 对象大小不符：' + key)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for position, _ in enumerate(pool.map(head, sorted(objects.items())), 1):
            if position % 500 == 0:
                print(f'OSS 已验证 {position}/{len(objects)}', flush=True)
    return len(objects)


def ensure_destination(payload):
    from django.db.models import Q
    from diary_presets.models import Template, Upload, ResourceTask
    indexed = validate_payload(payload)
    if connection.vendor == 'mysql':
        tables = {model(label)._meta.db_table for label in LABELS}
        tables.update(model(label)._meta.db_table for label in (
            'diary_presets.upload', 'diary_presets.resourceTask', 'diary_presets.downloadplan',
            'diary_presets.searchstate', 'material_library.libraryfavorite', 'material_library.materialfavorite'))
        with connection.cursor() as cursor:
            cursor.execute('SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()')
            engines = dict(cursor.fetchall())
        if any(engines.get(table, '').lower() != 'innodb' for table in tables):
            raise ValueError('缺少表或存在非 InnoDB 表，无法保证事务替换')
    incoming = list(indexed['diary_presets.template'])
    if Template.objects.filter(pk__in=incoming).exclude(audience='public').exists():
        raise ValueError('公开手帐 UUID 与服务器私人定制冲突')
    libraries = model('material_library.materiallibrary').objects
    if libraries.filter(pk__in=list(indexed['material_library.materiallibrary'])).exclude(template__audience='public').exists():
        raise ValueError('素材库 UUID 与服务器私人定制冲突')
    pending = Upload.objects.filter(template__audience='public').exclude(status__in=['done', 'failed', 'cancelled', 'ready'])
    tasks = ResourceTask.objects.filter(upload__template__audience='public').filter(Q(status='queued') | Q(status='processing'))
    if pending.exists() or tasks.exists():
        raise ValueError('服务器存在未完成的公开预设上传任务，请先处理后再同步')
    return indexed


def sync_product(record, fields):
    from django.db.models import Q
    table = model('print_orders.product')
    candidates = table.objects.filter(
        Q(pk=record['pk']) | Q(width_mm=fields['width_mm'], height_mm=fields['height_mm']))
    if candidates.count() > 1:
        raise ValueError('服务器印刷规格有重复匹配：' + fields['title'])
    instance = candidates.first()
    values = {name: table._meta.get_field(name).to_python(value) for name, value in fields.items()}
    if instance:
        changed = any(getattr(instance, name) != value for name, value in values.items() if name != 'revision')
        values['revision'] = max(instance.revision, values['revision']) + int(changed)
    else:
        instance = table(pk=record['pk'])
    for name, value in values.items():
        setattr(instance, name, value)
    instance.save()
    return instance


def delete_public():
    from diary_presets.models import Template, Version, Upload, DownloadPlan, Event, CatalogEntry, ResourceTask
    from material_library.models import MaterialLibrary, LibraryVersion, LibraryItem, LibraryFavorite
    templates = Template.objects.filter(audience='public')
    versions = Version.objects.filter(template__in=templates)
    libraries = MaterialLibrary.objects.filter(template__in=templates)
    old_materials = set(LibraryItem.objects.filter(version__library__in=libraries).values_list('material_id', flat=True))
    favorites = list(LibraryFavorite.objects.filter(library__in=libraries).values('id', 'user_id', 'library_id', 'created_at'))
    ResourceTask.objects.filter(upload__template__in=templates).delete()
    Upload.objects.filter(template__in=templates).delete()
    DownloadPlan.objects.filter(version__in=versions).delete()
    Event.objects.filter(template__in=templates).delete()
    CatalogEntry.objects.filter(version__in=versions).delete()
    LibraryItem.objects.filter(version__library__in=libraries).delete()
    libraries.update(current=None)
    LibraryVersion.objects.filter(library__in=libraries).delete()
    libraries.delete()
    templates.update(current=None)
    versions.delete()
    templates.delete()
    return old_materials, favorites


def mapped_fields(record, mapping):
    fields = deepcopy(record['fields'])
    for field in model(record['model'])._meta.fields:
        if field.remote_field and fields[field.name] is not None:
            fields[field.name] = mapping[field.remote_field.model._meta.label_lower][str(fields[field.name])]
    return fields


@transaction.atomic
def replace_catalog(payload):
    indexed = ensure_destination(payload)
    old_materials, favorites = delete_public()
    mapping = {label: {} for label in LABELS}
    for label in LABELS:
        table = model(label)
        for record in sorted(indexed[label].values(), key=lambda row: table._meta.pk.to_python(row['pk'])):
            initial = deepcopy(record)
            for name in DEFERRED.get(label, ()):
                initial['fields'][name] = None
            fields = mapped_fields(initial, mapping)
            if label == 'print_orders.product':
                instance = sync_product(record, fields)
            elif label in SHARED:
                key = SHARED[label]
                lookup = {'pk': record['pk']} if key == 'pk' else {key: fields[key]}
                defaults = {}
                for name, value in fields.items():
                    field = table._meta.get_field(name)
                    defaults[field.attname] = field.to_python(value)
                if label == 'material_library.material':
                    collision = table.objects.filter(source_identity=fields['source_identity']).exclude(pk=record['pk'])
                    if collision.exists():
                        raise ValueError('素材稳定身份发生 UUID 冲突')
                instance, _ = table.objects.update_or_create(**lookup, defaults=defaults)
            elif label == 'material_library.materialrevision':
                instance = table.objects.filter(material_id=fields['material'], digest=fields['digest']).first()
                if instance:
                    existing = dump_rows(table.objects.filter(pk=instance.pk))[0]['fields']
                    if canonical(existing) != canonical(fields):
                        raise ValueError('服务器存在不同内容的同摘要素材修订')
                else:
                    initial.update(pk=None, fields=fields)
                    deserialized = next(serializers.deserialize('python', [initial]))
                    deserialized.save()
                    instance = deserialized.object
            else:
                initial.update(fields=fields)
                if table._meta.pk.get_internal_type() in ('AutoField', 'BigAutoField', 'SmallAutoField'):
                    initial['pk'] = None
                deserialized = next(serializers.deserialize('python', [initial]))
                deserialized.save()
                instance = deserialized.object
            mapping[label][str(record['pk'])] = instance.pk
    for label, names in DEFERRED.items():
        for record in indexed[label].values():
            updates = {}
            for name in names:
                value = record['fields'][name]
                related = model(label)._meta.get_field(name).remote_field.model._meta.label_lower
                updates[name + '_id'] = mapping[related][str(value)] if value is not None else None
            model(label).objects.filter(pk=mapping[label][str(record['pk'])]).update(**updates)
    from material_library.models import Material, MaterialRevision, LibraryItem, MaterialLibrary, LibraryFavorite
    incoming_materials = set(mapping['material_library.material'].values())
    stale = Material.objects.filter(pk__in=old_materials - incoming_materials).exclude(
        pk__in=LibraryItem.objects.values('material_id'))
    MaterialRevision.objects.filter(material__in=stale).exclude(pk__in=LibraryItem.objects.values('revision_id')).delete()
    stale.delete()
    for favorite in favorites:
        if MaterialLibrary.objects.filter(pk=favorite['library_id']).exists():
            LibraryFavorite(**favorite).save_base(raw=True, force_insert=True)
    prune_shared(indexed, mapping)
    from django.db.models import F
    from print_orders.models import Product, Order
    stale_products = Product.objects.exclude(pk__in=mapping['print_orders.product'].values())
    stale_products.exclude(pk__in=Order.objects.values('product_id')).delete()
    stale_products.filter(active=True).update(active=False, revision=F('revision') + 1)
    state, _ = model('diary_presets.searchstate').objects.select_for_update().get_or_create(pk=1)
    state.revision = max(state.revision, payload['search_revision']) + 1
    state.save(update_fields=['revision'])
    connection.check_constraints()
    verify_import(indexed, mapping)
    return dict(counts={label: len(records) for label, records in indexed.items()}, search_revision=state.revision)


def prune_shared(indexed, mapping):
    from diary_presets.models import Series, SearchTaxon, CatalogEntryTerm
    Series.objects.exclude(pk__in=mapping['diary_presets.series'].values()).filter(templates__isnull=True).delete()
    keep = set(indexed['diary_presets.searchtaxon'])
    keep.update(CatalogEntryTerm.objects.values_list('taxon_id', flat=True))
    while True:
        parents = set()
        for parent, merged in SearchTaxon.objects.filter(pk__in=keep).values_list('parent_id', 'merged_into_id'):
            parents.update(value for value in (parent, merged) if value)
        if parents <= keep:
            break
        keep.update(parents)
    stale = SearchTaxon.objects.exclude(pk__in=keep)
    stale.update(parent=None, merged_into=None)
    stale.delete()


def verify_import(indexed, mapping):
    for label in LABELS:
        for record in indexed[label].values():
            expected = mapped_fields(record, mapping)
            actual = dump_rows(model(label).objects.filter(pk=mapping[label][str(record['pk'])]))
            if label == 'print_orders.product' and actual:
                if actual[0]['fields']['revision'] < expected['revision']:
                    raise ValueError('印刷规格修订号倒退')
                expected['revision'] = actual[0]['fields']['revision']
            if len(actual) != 1 or canonical(actual[0]['fields']) != canonical(expected):
                raise ValueError('导入后逐行核对失败：' + label)
    actual = set(str(value) for value in model('diary_presets.template').objects.filter(audience='public').values_list('pk', flat=True))
    if actual != set(indexed['diary_presets.template']):
        raise ValueError('服务器公开手帐目录未完全替换')


def configure(env_file=None):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, '/app' if Path('/app/manage.py').exists() else str(root))
    if env_file:
        from dotenv import dotenv_values
        path = Path(env_file)
        if path.stat().st_mode & 0o077:
            raise ValueError('本地配置权限必须为 600')
        values = dotenv_values(path, interpolate=False)
        if values.get('DB_ENGINE') != 'django.db.backends.mysql' or values.get('DB_HOST') not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('导出仅允许工具配置指向本机 MySQL')
        if values.get('DB_NAME') != 'sparkservice':
            raise ValueError('本地源数据库必须为 sparkservice')
        os.environ.update({key: value for key, value in values.items() if value is not None})
    os.environ['DJANGO_SETTINGS_MODULE'] = 'SparkService.settings'
    import django
    django.setup()
    if connection.settings_dict['NAME'] != 'sparkservice' or connection.vendor != 'mysql':
        raise ValueError('实际数据库不是预期的 MySQL sparkservice')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('export', 'check', 'apply'))
    parser.add_argument('package', type=Path)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--verified-report', type=Path)
    args = parser.parse_args()
    try:
        configure(args.env_file)
        if args.action == 'export':
            payload = export_catalog()
            args.package.write_text(canonical(payload), encoding='utf-8')
            report = dict(sha256=checksum(payload), counts={label: sum(record['model'] == label for record in payload['records']) for label in LABELS}, oss=payload['oss'])
        else:
            payload = json.loads(args.package.read_text(encoding='utf-8'))
            ensure_destination(payload)
            if args.action == 'check':
                count = check_oss(payload)
                report = dict(sha256=checksum(payload), oss=oss_location(), objects_verified=count)
            else:
                if os.getenv('RELEASE_TARGET_IP') != '39.106.39.110' or not args.verified_report:
                    raise ValueError('导入只能由目标服务器同步入口执行')
                verified = json.loads(args.verified_report.read_text(encoding='utf-8'))
                if verified['sha256'] != checksum(payload) or verified['oss'] != oss_location():
                    raise ValueError('包摘要或 OSS 归属在预检后改变')
                report = replace_catalog(payload)
                report['sha256'] = checksum(payload)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, cls=DjangoJSONEncoder), flush=True)
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print('预设同步失败：' + message, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
