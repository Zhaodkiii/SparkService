# Generated manually for access deny blacklist

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_device_identity_login"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccessDenyEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "dimension",
                    models.CharField(
                        choices=[("user_id", "用户 ID"), ("phone", "手机号"), ("email", "邮箱")],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("dimension_value", models.CharField(db_index=True, max_length=255)),
                ("reason_code", models.CharField(db_index=True, default="account_banned", max_length=64)),
                (
                    "reason_note",
                    models.TextField(blank=True, db_comment="后台内部备注，不返回客户端", default=""),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[("admin", "后台手动"), ("auto_expand", "用户封禁自动展开")],
                        db_index=True,
                        default="admin",
                        max_length=32,
                    ),
                ),
                (
                    "related_user_id",
                    models.IntegerField(
                        blank=True,
                        db_comment="关联用户 ID（展示用）",
                        db_index=True,
                        null=True,
                    ),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        blank=True,
                        db_comment="空=永久",
                        db_index=True,
                        null=True,
                    ),
                ),
                ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_by_id", models.IntegerField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "访问拒绝条目",
                "verbose_name_plural": "访问拒绝条目",
                "db_table_comment": "登录注册黑名单：有效条目按 dimension+dimension_value 唯一",
                "indexes": [
                    models.Index(fields=["dimension", "dimension_value", "revoked_at"], name="accounts_ac_dimensi_6a8f2d_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("revoked_at__isnull", True)),
                        fields=("dimension", "dimension_value"),
                        name="uniq_access_deny_active_dimension_value",
                    ),
                ],
            },
        ),
    ]
