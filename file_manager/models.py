import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def upload_to(instance, filename):
    return f"managed_files/{instance.user_id}/{instance.file_uuid}/{filename}"


class ManagedFile(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="managed_files", on_delete=models.CASCADE, db_index=True)
    file_uuid = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    file = models.FileField(upload_to=upload_to, max_length=512)
    original_name = models.CharField(max_length=255)
    file_ext = models.CharField(max_length=32, blank=True, default="")
    mime_type = models.CharField(max_length=128, blank=True, default="application/octet-stream")
    file_size = models.BigIntegerField(default=0)
    file_md5 = models.CharField(max_length=64, blank=True, default="")
    is_public = models.BooleanField(default=False, db_index=True)
    business_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    business_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "is_deleted", "updated_at"]),
            models.Index(fields=["user", "business_type", "business_id", "is_deleted"]),
        ]

    def soft_delete(self):
        if self.is_deleted:
            return
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def __str__(self):
        return f"{self.id}:{self.original_name}"
