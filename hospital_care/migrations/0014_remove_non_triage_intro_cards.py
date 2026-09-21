from django.db import migrations


REMOVED_KINDS = ("chatGuideCard",)


def remove_non_triage_intro_cards(apps, schema_editor):
    """Remove generic cards previously seeded into AI triage conversations."""
    HospitalAITriageBinding = apps.get_model("hospital_care", "HospitalAITriageBinding")
    ChatMessage = apps.get_model("chat_sync", "ChatMessage")
    ChatMessageBlock = apps.get_model("chat_sync", "ChatMessageBlock")

    triage_thread_ids = HospitalAITriageBinding.objects.values_list("thread_id", flat=True)
    target_blocks = ChatMessageBlock.objects.filter(
        thread_id__in=triage_thread_ids,
        kind__in=REMOVED_KINDS,
    )
    affected_message_ids = list(target_blocks.values_list("message_id", flat=True).distinct())
    target_blocks.delete()

    if affected_message_ids:
        ChatMessage.objects.filter(id__in=affected_message_ids, blocks__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("hospital_care", "0013_align_ai_triage_thread_collation"),
    ]

    operations = [
        migrations.RunPython(remove_non_triage_intro_cards, migrations.RunPython.noop),
    ]
