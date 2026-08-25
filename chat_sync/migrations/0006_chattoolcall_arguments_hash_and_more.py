import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat_sync', '0005_chat_ai_unified_context'),
    ]

    operations = [
        migrations.AddField(
            model_name='chattoolcall',
            name='arguments_hash',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='attempt_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='call_index',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='canonical_name',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='duplicate_of',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='duplicates', to='chat_sync.chattoolcall'),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='error_code',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='error_message',
            field=models.CharField(blank=True, default='', max_length=512),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='execution_key',
            field=models.CharField(blank=True, db_index=True, default='', max_length=160),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='max_attempts',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='policy_version',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='provider_index',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='result_content',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='result_metadata',
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='retryable',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='round_index',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='schema_hash',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='chattoolcall',
            name='source_refs',
            field=models.JSONField(default=list),
        ),
        migrations.CreateModel(
            name='ChatAgentCheckpoint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('revision', models.PositiveIntegerField(default=1)),
                ('next_round_index', models.PositiveIntegerField(default=0)),
                ('tool_steps', models.PositiveIntegerField(default=0)),
                ('transcript', models.JSONField(default=list)),
                ('checkpoint_boundary', models.CharField(default='round', max_length=32)),
                ('tool_manifest_hash', models.CharField(blank=True, default='', max_length=64)),
                ('context_hash', models.CharField(blank=True, default='', max_length=64)),
                ('transcript_hash', models.CharField(blank=True, default='', max_length=64)),
                ('status', models.CharField(choices=[('ready', 'Ready'), ('superseded', 'Superseded')], default='ready', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('context_snapshot', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='chat_sync.chatturncontextsnapshot')),
                ('run', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='agent_checkpoint', to='chat_sync.chatrun')),
            ],
            options={
                'db_table': 'chat_sync_ai_agent_checkpoint',
                'indexes': [models.Index(fields=['run', 'status'], name='idx_ai_checkpoint_run_status')],
            },
        ),
        # Keep the checkpoint table's string columns compatible with the
        # utf8mb4_unicode_ci collation used by the existing chat tables and
        # the AI run tables created in migration 0003.
        migrations.RunSQL(
            sql="""
                ALTER TABLE `chat_sync_ai_agent_checkpoint`
                    CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
