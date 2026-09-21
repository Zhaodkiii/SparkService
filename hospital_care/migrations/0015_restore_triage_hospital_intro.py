from django.db import migrations


def restore_hospital_intro_cards(apps, schema_editor):
    HospitalAITriageBinding = apps.get_model("hospital_care", "HospitalAITriageBinding")
    ChatMessage = apps.get_model("chat_sync", "ChatMessage")
    ChatMessageBlock = apps.get_model("chat_sync", "ChatMessageBlock")
    Member = apps.get_model("medical", "Member")

    for binding in HospitalAITriageBinding.objects.select_related("thread", "hospital"):
        if ChatMessageBlock.objects.filter(thread_id=binding.thread_id, kind="hospitalTriageIntroCard").exists():
            continue
        member = Member.objects.filter(pk=binding.thread.member_id).only("name").first()
        now = binding.updated_at
        message = ChatMessage.objects.create(
            user_id=binding.thread.user_id,
            thread_id=binding.thread_id,
            role="system",
            client_message_id=binding.thread_id,
            server_message_id=binding.thread_id,
            delivery_state="sent",
            created_at=now,
        )
        ChatMessageBlock.objects.create(
            id=binding.thread_id,
            user_id=binding.thread.user_id,
            thread_id=binding.thread_id,
            message_id=message.id,
            kind="hospitalTriageIntroCard",
            status="ready",
            revision=1,
            order_key=900,
            node_role="timeline",
            payload={"hospital_triage_intro_card": {"_0": {
                "hospital_name": binding.hospital.name,
                "hospital_short_name": binding.hospital.short_name or binding.hospital.name,
                "member_id": binding.thread.member_id,
                "member_display_name": (member.name if member else "") or "患者",
                "service_title": "AI 导诊",
                "introduction_excerpt": (binding.hospital.introduction or "").strip()[:160],
            }}},
            created_at=now,
            updated_at=now,
        )


class Migration(migrations.Migration):
    dependencies = [("hospital_care", "0014_remove_non_triage_intro_cards")]
    operations = [migrations.RunPython(restore_hospital_intro_cards, migrations.RunPython.noop)]
