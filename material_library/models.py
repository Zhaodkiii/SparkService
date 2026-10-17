import uuid
from django.conf import settings
from django.db import models


class ResourceBlob(models.Model):
    sha256 = models.CharField(max_length=64, primary_key=True)
    object_key = models.CharField(max_length=1024)
    byte_size = models.PositiveBigIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    mime = models.CharField(max_length=40)


class Material(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_identity = models.CharField(max_length=240, unique=True)
    material_type = models.CharField(max_length=16, choices=[('sticker', '贴纸'), ('background', '背景')])
    active = models.BooleanField(default=True)


class MaterialRevision(models.Model):
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name='revisions')
    digest = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=32)
    subcategory = models.CharField(max_length=32)
    keywords = models.JSONField(default=list)
    aliases = models.JSONField(default=list)
    resource = models.ForeignKey(ResourceBlob, on_delete=models.PROTECT, related_name='+')
    thumbnail = models.ForeignKey(ResourceBlob, on_delete=models.PROTECT, related_name='+')
    sources = models.JSONField(default=list)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['material', 'digest'], name='material_revision_digest')]


class MaterialLibrary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey('diary_presets.Template', on_delete=models.PROTECT, related_name='material_libraries')
    library_type = models.CharField(max_length=16, choices=[('sticker', '贴纸'), ('background', '背景')])
    title = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    current = models.ForeignKey('LibraryVersion', null=True, on_delete=models.PROTECT, related_name='+')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['template', 'library_type'], name='template_library_type')]


class LibraryVersion(models.Model):
    library = models.ForeignKey(MaterialLibrary, on_delete=models.PROTECT, related_name='versions')
    number = models.PositiveIntegerField()
    preset_version = models.ForeignKey('diary_presets.Version', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['library', 'number'], name='library_version_number')]


class LibraryItem(models.Model):
    version = models.ForeignKey(LibraryVersion, on_delete=models.CASCADE, related_name='items')
    revision = models.ForeignKey(MaterialRevision, on_delete=models.PROTECT)
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['version', 'material'], name='library_unique_material')]


class LibraryFavorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    library = models.ForeignKey(MaterialLibrary, on_delete=models.CASCADE, related_name='favorites')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'library'], name='user_library_favorite')]


class MaterialFavorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='favorites')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'material'], name='user_material_favorite')]
