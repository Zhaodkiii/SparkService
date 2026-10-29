import hashlib
import json
from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import MaterialLibrary, LibraryVersion, LibraryItem, MaterialRevision, TemplateLibraryBinding
from .catalog import validate_category


def revision(material, data):
    try: validate_category(data['kind'], data['subcategory'], material.material_type)
    except ValueError as error: raise ValidationError(str(error))
    for field in ('keywords', 'aliases'):
        values = data.get(field, [])
        if not isinstance(values, list) or len(values) > 40 or any(not isinstance(v, str) or len(v) > 60 for v in values):
            raise ValidationError('关键词必须为最多 40 个短文本')
        data[field] = list(dict.fromkeys(v.strip() for v in values if v.strip()))
    if not isinstance(data['name'], str) or not 1 <= len(data['name']) <= 120:
        raise ValidationError('名称长度必须为 1—120')
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return MaterialRevision.objects.get_or_create(material=material, digest=digest, defaults=data)[0]


@transaction.atomic
def publish_library(library, revisions, expected):
    library = MaterialLibrary.objects.select_for_update().get(pk=library.pk)
    actual = library.current.number if library.current_id else 0
    if expected != actual:
        raise ValidationError('库已更新，请刷新后重新提交')
    if library.deleted_at: raise ValidationError('素材包已删除，请先恢复')
    if not library.template.current_id:
        raise ValidationError('请先发布手帐预设')
    if len({r.material_id for r in revisions}) != len(revisions):
        raise ValidationError('同一素材不能重复加入库')
    if any(r.material.material_type != library.library_type for r in revisions):
        raise ValidationError('素材类型不匹配')
    old = list(library.current.items.values_list('revision_id', flat=True)) if library.current_id else None
    if old == [r.pk for r in revisions] and library.current.preset_version_id == library.template.current_id:
        return library.current
    version = LibraryVersion.objects.create(library=library, number=actual + 1, preset_version=library.template.current)
    LibraryItem.objects.bulk_create([LibraryItem(version=version, revision=r, material=r.material, position=i) for i, r in enumerate(revisions)])
    from .models import TemplateMaterialLink
    TemplateMaterialLink.objects.filter(library=library, library_version__isnull=True).update(library_version=version)
    library.current = version
    from django.utils import timezone
    if library.first_published_at is None: library.first_published_at=timezone.now()
    library.state_revision+=1
    library.save(update_fields=['current','first_published_at','state_revision'])
    return version
