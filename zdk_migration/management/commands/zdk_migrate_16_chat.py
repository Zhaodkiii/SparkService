import json
import uuid

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.utils import timezone

from chat_sync.models import ChatMessage, ChatMessageBlock, ChatThread
from chat_sync.signals import on_chat_message_saved

from zdk_migration.lib.base import ZdkMigrateCommand
from zdk_migration.lib.old_db import old_fetch_all, old_select, old_table_exists
from zdk_migration.lib.transforms import (
    chat_block_payload,
    chat_role_to_new,
    json_safe_value,
    legacy_chat_anchor_is_invalid,
    normalize_legacy_chat_attachment,
    parse_json_value,
)


class Command(ZdkMigrateCommand):
    help = "Migrate messaging conversations/messages to chat_sync threads/messages/blocks"

    def _update_thread_metadata(self, thread: ChatThread, row: dict) -> bool:
        changed = False

        # Title/deleted flags should track legacy conversation on re-runs.
        title = (row.get("title") or "Migrated Chat")[:255]
        if (thread.title or "") != title:
            thread.title = title
            changed = True
        is_deleted = bool(row.get("is_deleted"))
        if thread.is_deleted != is_deleted:
            thread.is_deleted = is_deleted
            changed = True
        if thread.deleted_at != row.get("deleted_at"):
            thread.deleted_at = row.get("deleted_at")
            changed = True

        # New thread decoration fields (added in ChatThread).
        if "icon_name" in row:
            icon_name = (row.get("icon_name") or "")[:128]
            if (thread.icon_name or "") != icon_name:
                thread.icon_name = icon_name
                changed = True
        if "icon_color_name" in row:
            icon_color_name = (row.get("icon_color_name") or "")[:64]
            if (thread.icon_color_name or "") != icon_color_name:
                thread.icon_color_name = icon_color_name
                changed = True
        if "is_pinned" in row:
            is_pinned = bool(row.get("is_pinned"))
            if thread.is_pinned != is_pinned:
                thread.is_pinned = is_pinned
                changed = True
        if "pinned_at" in row:
            if thread.pinned_at != row.get("pinned_at"):
                thread.pinned_at = row.get("pinned_at")
                changed = True

        if changed and not self.dry_run:
            thread.save(
                update_fields=[
                    "title",
                    "icon_name",
                    "icon_color_name",
                    "is_pinned",
                    "pinned_at",
                    "is_deleted",
                    "deleted_at",
                    "updated_at",
                ]
            )
        return changed

    def run_migration(self) -> None:
        post_save.disconnect(on_chat_message_saved, sender=ChatMessage)
        try:
            if not old_table_exists("messaging_conversation"):
                return
            User = get_user_model()
            conversations = old_select(
                "messaging_conversation",
                [
                    "id",
                    "user_id",
                    "type",
                    "assistant_id",
                    "title",
                    "role_config",
                    "created_at",
                    "updated_at",
                    "last_message_at",
                    "is_deleted",
                    "deleted_at",
                    "icon_name",
                    "icon_color_name",
                    "is_pinned",
                    "pinned_at",
                ],
                order_by="created_at, id",
            )
            self.stdout.write(f"Found {len(conversations)} conversations")
            for row in conversations:
                old_id = row["id"]
                skip, mapped_id = self.resolve_mapped_row("conversation", old_id, ChatThread)
                if skip and mapped_id:
                    thread = ChatThread.objects.get(pk=mapped_id)
                    self._update_thread_metadata(thread, row)
                    self._migrate_messages(old_id, thread.id, thread.user_id)
                    self.stats.skipped += 1
                    continue

                if not User.objects.filter(pk=row["user_id"]).exists():
                    self.log_skip(f"conversation user missing id={row['user_id']}")
                    continue
                if self.dry_run:
                    self.id_map.set("conversation", old_id, old_id)
                    self.stats.migrated += 1
                    continue

                role_config = parse_json_value(row.get("role_config"), default={})
                role_prompt = ""
                if isinstance(role_config, dict):
                    role_prompt = json.dumps(role_config, ensure_ascii=False)

                thread_id = uuid.uuid4()

                def _create_thread(row=row, old_id=old_id, role_prompt=role_prompt, thread_id=thread_id):
                    thread = ChatThread.objects.create(
                        id=thread_id,
                        user_id=row["user_id"],
                        title=(row.get("title") or "Migrated Chat")[:255],
                        scenario="chat",
                        role_prompt=role_prompt[:10000] if role_prompt else "",
                        icon_name=(row.get("icon_name") or "")[:128],
                        icon_color_name=(row.get("icon_color_name") or "")[:64],
                        is_pinned=bool(row.get("is_pinned")) if "is_pinned" in row else False,
                        pinned_at=row.get("pinned_at"),
                        is_deleted=bool(row.get("is_deleted")),
                        deleted_at=row.get("deleted_at"),
                    )
                    ChatThread.objects.filter(pk=thread.pk).update(
                        created_at=row.get("created_at") or thread.created_at,
                        updated_at=row.get("updated_at") or thread.updated_at,
                    )
                    return str(thread.id)

                try:
                    new_thread_id = _create_thread()
                    self.id_map.set("conversation", old_id, new_thread_id)
                    self.stats.migrated += 1
                except Exception as exc:
                    self.log_fail(f"conversation:{old_id}", exc)
                    continue

                self._migrate_messages(old_id, uuid.UUID(new_thread_id), row["user_id"])

            repaired = self._repair_legacy_chat_blocks()
            if repaired:
                self.stdout.write(f"Repaired {repaired} legacy chat blocks")
        finally:
            post_save.connect(on_chat_message_saved, sender=ChatMessage)

    def _migrate_messages(self, old_conversation_id: str, thread_id: uuid.UUID, user_id: int) -> None:
        if not old_table_exists("messaging_message"):
            return
        messages = old_fetch_all(
            """
            SELECT id, conversation_id, role, content, created_at, message_type, message_metadata,
                   attachments, is_refusal, is_local, is_run_step, synced_at, is_deleted, deleted_at
            FROM messaging_message
            WHERE conversation_id = %s
            ORDER BY created_at, id
            """,
            (old_conversation_id,),
        )
        for row in messages:
            if self.dry_run:
                return
            client_message_id = uuid.uuid5(uuid.NAMESPACE_URL, f"zdk-msg:{row['id']}")
            server_message_id = f"zdk_{row['id']}"[:64]
            existing = ChatMessage.objects.filter(user_id=user_id, client_message_id=client_message_id).first()
            if existing:
                self._repair_message_blocks(existing, row)
                continue

            metadata = self._build_message_metadata(row, old_conversation_id)
            created_at = row.get("created_at") or timezone.now()

            def _create_message(row=row, metadata=metadata, created_at=created_at):
                message = ChatMessage.objects.create(
                    user_id=user_id,
                    thread_id=thread_id,
                    role=chat_role_to_new(row.get("role")),
                    client_message_id=client_message_id,
                    server_message_id=server_message_id,
                    delivery_state=ChatMessage.DeliveryState.SENT,
                    tombstone=bool(row.get("is_deleted")),
                    metadata=metadata,
                    created_at=created_at,
                )
                self._create_text_block(message, row, created_at)
                self._create_attachment_blocks(message, row, created_at)
                return message

            if self.run_safe(f"message:{row['id']}", _create_message):
                self.stats.migrated += 1

    def _build_message_metadata(self, row: dict, old_conversation_id: str) -> dict:
        legacy_metadata = parse_json_value(row.get("message_metadata"), default={})
        metadata = dict(legacy_metadata) if isinstance(legacy_metadata, dict) else {}
        if legacy_metadata and not isinstance(legacy_metadata, dict):
            metadata["legacy_message_metadata"] = json_safe_value(legacy_metadata)

        metadata["legacy_message_id"] = row["id"]
        metadata["legacy_conversation_id"] = old_conversation_id
        if row.get("message_type"):
            metadata["legacy_message_type"] = row.get("message_type")
            metadata.setdefault("messageType", row.get("message_type"))
        for old_key, new_key in (
            ("is_refusal", "legacy_is_refusal"),
            ("is_local", "legacy_is_local"),
            ("is_run_step", "legacy_is_run_step"),
            ("synced_at", "legacy_synced_at"),
            ("deleted_at", "legacy_deleted_at"),
        ):
            if row.get(old_key) is not None:
                metadata[new_key] = json_safe_value(row.get(old_key))

        attachments = self._normalized_legacy_attachments(row)
        if attachments:
            metadata["attachments"] = attachments
        return json_safe_value(metadata)

    def _create_text_block(self, message: ChatMessage, row: dict, created_at) -> None:
        order_base = float(message.id)
        block_id = uuid.uuid5(uuid.NAMESPACE_URL, f"zdk-block:{row['id']}")
        text_payload = chat_block_payload(
            block_id=str(block_id),
            kind="text",
            order_key=order_base,
            created_at=created_at,
            updated_at=created_at,
            text=row.get("content") or "",
        )
        ChatMessageBlock.objects.create(
            id=block_id,
            user_id=message.user_id,
            thread_id=message.thread_id,
            message_id=message.id,
            kind="text",
            status=ChatMessageBlock.Status.READY,
            revision=1,
            order_key=order_base,
            payload=text_payload,
            anchor=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def _extract_legacy_attachments(self, row: dict) -> list[dict]:
        attachments = parse_json_value(row.get("attachments"), default=[])
        if isinstance(attachments, list) and attachments:
            return attachments
        metadata = parse_json_value(row.get("message_metadata"), default={}) or {}
        if isinstance(metadata, dict):
            report = metadata.get("reportData") if isinstance(metadata.get("reportData"), dict) else None
            if report and isinstance(report.get("attachmentsJSON"), str):
                parsed = parse_json_value(report.get("attachmentsJSON"), default=[])
                if isinstance(parsed, list):
                    return parsed
        return []

    def _normalized_legacy_attachments(self, row: dict) -> list[dict]:
        attachments = self._extract_legacy_attachments(row)
        if not attachments:
            return []
        normalized = [normalize_legacy_chat_attachment(att) for att in attachments]
        return [att for att in normalized if att and (att.get("url") or att.get("fileId") or att.get("text"))]

    def _create_image_gallery_block(self, message: ChatMessage, row: dict, created_at) -> None:
        self._create_attachment_blocks(message, row, created_at, include_files=False)

    def _create_attachment_blocks(
        self,
        message: ChatMessage,
        row: dict,
        created_at,
        *,
        include_files: bool = True,
    ) -> None:
        normalized = self._normalized_legacy_attachments(row)
        if not normalized:
            return
        images = [att for att in normalized if att.get("type") == "image" and att.get("url")]
        files = [att for att in normalized if att.get("type") != "image"]

        order_base = float(message.id)
        if images:
            gallery_id = uuid.uuid5(uuid.NAMESPACE_URL, f"zdk-block-gallery:{row['id']}")
            if ChatMessageBlock.objects.filter(message=message, id=gallery_id).exists():
                images = []
        if images:
            gallery_payload = chat_block_payload(
                block_id=str(gallery_id),
                kind="imageGallery",
                order_key=order_base + 0.001,
                created_at=created_at,
                updated_at=created_at,
                attachments=images,
            )
            ChatMessageBlock.objects.create(
                id=gallery_id,
                user_id=message.user_id,
                thread_id=message.thread_id,
                message_id=message.id,
                kind="imageGallery",
                status=ChatMessageBlock.Status.READY,
                revision=1,
                order_key=order_base + 0.001,
                payload=gallery_payload,
                anchor=None,
                created_at=created_at,
                updated_at=created_at,
            )

        if include_files and files:
            files_id = uuid.uuid5(uuid.NAMESPACE_URL, f"zdk-block-files:{row['id']}")
            if ChatMessageBlock.objects.filter(message=message, id=files_id).exists():
                files = []
        if include_files and files:
            files_payload = chat_block_payload(
                block_id=str(files_id),
                kind="fileAttachments",
                order_key=order_base + 0.002,
                created_at=created_at,
                updated_at=created_at,
                attachments=files,
            )
            ChatMessageBlock.objects.create(
                id=files_id,
                user_id=message.user_id,
                thread_id=message.thread_id,
                message_id=message.id,
                kind="fileAttachments",
                status=ChatMessageBlock.Status.READY,
                revision=1,
                order_key=order_base + 0.002,
                payload=files_payload,
                anchor=None,
                created_at=created_at,
                updated_at=created_at,
            )

    def _repair_message_blocks(self, message: ChatMessage, row: dict) -> None:
        """Fix blocks for messages that were migrated with invalid anchor/kind/payload."""
        created_at = row.get("created_at") or message.created_at
        order_base = float(message.id)
        text_block_id = uuid.uuid5(uuid.NAMESPACE_URL, f"zdk-block:{row['id']}")
        text_block = ChatMessageBlock.objects.filter(id=text_block_id, message=message).first()
        text_payload = chat_block_payload(
            block_id=str(text_block_id),
            kind="text",
            order_key=order_base,
            created_at=created_at,
            updated_at=created_at,
            text=row.get("content") or "",
        )
        if text_block:
            changed = False
            if legacy_chat_anchor_is_invalid(text_block.anchor):
                text_block.anchor = None
                changed = True
            if text_block.kind != "text" or (text_block.payload or {}).get("kind") != "text":
                text_block.kind = "text"
                text_block.payload = text_payload
                changed = True
            elif text_block.payload != text_payload:
                text_block.payload = text_payload
                changed = True
            if changed and not self.dry_run:
                text_block.save(update_fields=["anchor", "kind", "payload", "updated_at"])
                self.stats.migrated += 1
        elif not self.dry_run:
            ChatMessageBlock.objects.create(
                id=text_block_id,
                user_id=message.user_id,
                thread_id=message.thread_id,
                message_id=message.id,
                kind="text",
                status=ChatMessageBlock.Status.READY,
                revision=1,
                order_key=order_base,
                payload=text_payload,
                anchor=None,
                created_at=created_at,
                updated_at=created_at,
            )
            self.stats.migrated += 1

        # Rebuild image gallery if legacy had images.
        gallery_id = uuid.uuid5(uuid.NAMESPACE_URL, f"zdk-block-gallery:{row['id']}")
        if not ChatMessageBlock.objects.filter(message=message, id=gallery_id).exists() and not self.dry_run:
            self._create_image_gallery_block(message, row, created_at)

        files_id = uuid.uuid5(uuid.NAMESPACE_URL, f"zdk-block-files:{row['id']}")
        if not ChatMessageBlock.objects.filter(message=message, id=files_id).exists() and not self.dry_run:
            self._create_attachment_blocks(message, row, created_at)

        metadata = self._build_message_metadata(row, row.get("conversation_id"))
        if message.metadata != metadata and not self.dry_run:
            message.metadata = metadata
            message.save(update_fields=["metadata", "server_updated_at"])
            self.stats.migrated += 1

        non_supported = ChatMessageBlock.objects.filter(message=message).exclude(kind__in=["text", "imageGallery", "fileAttachments"])
        if non_supported.exists() and not self.dry_run:
            deleted, _ = non_supported.delete()
            self.stats.migrated += deleted

    def _repair_legacy_chat_blocks(self) -> int:
        repaired = 0
        invalid_anchor_blocks = ChatMessageBlock.objects.exclude(anchor__isnull=True)
        for block in invalid_anchor_blocks.iterator():
            if not legacy_chat_anchor_is_invalid(block.anchor):
                continue
            if self.dry_run:
                repaired += 1
                continue
            block.anchor = None
            block.save(update_fields=["anchor", "updated_at"])
            repaired += 1

        non_text_blocks = ChatMessageBlock.objects.exclude(kind__in=["text", "imageGallery", "fileAttachments"])
        non_text_count = non_text_blocks.count()
        if non_text_count:
            repaired += non_text_count
            if not self.dry_run:
                non_text_blocks.delete()

        for block in ChatMessageBlock.objects.filter(kind="text").iterator():
            payload = block.payload or {}
            enum_payload = payload.get("payload")
            if (
                payload.get("kind") == "text"
                and "text" in payload
                and isinstance(enum_payload, dict)
                and isinstance(enum_payload.get("text"), dict)
                and "_0" in enum_payload["text"]
            ):
                continue
            text = payload.get("text") or ""
            new_payload = chat_block_payload(
                block_id=str(block.id),
                kind="text",
                order_key=block.order_key or float(block.message_id),
                created_at=block.created_at,
                updated_at=block.updated_at,
                text=text,
            )
            if self.dry_run:
                repaired += 1
                continue
            block.payload = new_payload
            if legacy_chat_anchor_is_invalid(block.anchor):
                block.anchor = None
            block.save(update_fields=["payload", "anchor", "updated_at"])
            repaired += 1

        for block in ChatMessageBlock.objects.filter(kind="imageGallery").iterator():
            payload = block.payload or {}
            enum_payload = payload.get("payload")
            if (
                payload.get("kind") == "imageGallery"
                and isinstance(enum_payload, dict)
                and isinstance(enum_payload.get("imageGallery"), dict)
                and "_0" in enum_payload["imageGallery"]
            ):
                continue
            attachments = payload.get("attachments") or []
            if isinstance(attachments, list):
                normalized = [normalize_legacy_chat_attachment(att) for att in attachments]
                normalized = [att for att in normalized if att and att.get("type") == "image" and att.get("url")]
            else:
                normalized = []
            new_payload = chat_block_payload(
                block_id=str(block.id),
                kind="imageGallery",
                order_key=block.order_key or float(block.message_id),
                created_at=block.created_at,
                updated_at=block.updated_at,
                attachments=normalized,
            )
            if self.dry_run:
                repaired += 1
                continue
            block.payload = new_payload
            if legacy_chat_anchor_is_invalid(block.anchor):
                block.anchor = None
            block.save(update_fields=["payload", "anchor", "updated_at"])
            repaired += 1
        for block in ChatMessageBlock.objects.filter(kind="fileAttachments").iterator():
            payload = block.payload or {}
            enum_payload = payload.get("payload")
            if (
                payload.get("kind") == "fileAttachments"
                and isinstance(enum_payload, dict)
                and isinstance(enum_payload.get("fileAttachments"), dict)
                and "_0" in enum_payload["fileAttachments"]
            ):
                continue
            attachments = payload.get("attachments") or []
            if isinstance(attachments, list):
                normalized = [normalize_legacy_chat_attachment(att) for att in attachments]
                normalized = [att for att in normalized if att and att.get("type") != "image"]
            else:
                normalized = []
            new_payload = chat_block_payload(
                block_id=str(block.id),
                kind="fileAttachments",
                order_key=block.order_key or float(block.message_id),
                created_at=block.created_at,
                updated_at=block.updated_at,
                attachments=normalized,
            )
            if self.dry_run:
                repaired += 1
                continue
            block.payload = new_payload
            if legacy_chat_anchor_is_invalid(block.anchor):
                block.anchor = None
            block.save(update_fields=["payload", "anchor", "updated_at"])
            repaired += 1
        return repaired
