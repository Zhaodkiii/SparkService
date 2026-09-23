from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="RevenueCatCustomerIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("app_user_id", models.CharField(db_index=True, max_length=100, unique=True)),
                ("last_sync_attempt_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_successful_sync_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("last_sync_error_code", models.CharField(blank=True, default="", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="revenuecat_identity", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "RevenueCat 用户身份", "verbose_name_plural": "RevenueCat 用户身份"},
        ),
        migrations.CreateModel(
            name="RevenueCatWebhookEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.CharField(db_index=True, max_length=128, unique=True)),
                ("event_type", models.CharField(blank=True, default="", max_length=64)),
                ("app_user_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("environment", models.CharField(blank=True, db_index=True, default="", max_length=16)),
                ("event_timestamp_ms", models.BigIntegerField(default=0)),
                ("payload", models.JSONField()),
                ("process_status", models.CharField(choices=[("received", "已接收"), ("processing", "处理中"), ("processed", "已处理"), ("unmatched", "待匹配"), ("retryable", "待重试"), ("failed", "失败")], db_index=True, default="received", max_length=16)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("next_retry_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, default="", max_length=64)),
                ("error_message", models.TextField(blank=True, default="")),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("matched_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="revenuecat_webhook_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "RevenueCat Webhook 事件", "verbose_name_plural": "RevenueCat Webhook 事件", "indexes": [models.Index(fields=["process_status", "next_retry_at", "received_at"], name="subscriptio_process_024c30_idx")]},
        ),
        migrations.CreateModel(
            name="RevenueCatEntitlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entitlement_identifier", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("active", "有效"), ("expired", "已过期"), ("revoked", "已撤销"), ("unknown", "未知")], db_index=True, default="unknown", max_length=16)),
                ("environment", models.CharField(choices=[("production", "生产"), ("sandbox", "沙盒")], db_index=True, max_length=16)),
                ("product_id", models.CharField(blank=True, default="", max_length=255)),
                ("store", models.CharField(blank=True, default="", max_length=32)),
                ("period_type", models.CharField(blank=True, default="", max_length=32)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("will_renew", models.BooleanField(default=False)),
                ("original_transaction_id", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("provider_updated_at", models.DateTimeField(blank=True, null=True)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revenuecat_entitlements", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "RevenueCat 权益快照", "verbose_name_plural": "RevenueCat 权益快照", "indexes": [models.Index(fields=["user", "environment", "status", "expires_at"], name="subscriptio_user_id_771260_idx")]},
        ),
        migrations.CreateModel(
            name="RevenueCatCustomerAlias",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("alias", models.CharField(db_index=True, max_length=255, unique=True)),
                ("source", models.CharField(choices=[("login_result", "登录结果"), ("webhook", "Webhook"), ("server_sync", "服务端同步")], max_length=32)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("identity", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="aliases", to="subscriptions.revenuecatcustomeridentity")),
            ],
            options={"verbose_name": "RevenueCat 用户别名", "verbose_name_plural": "RevenueCat 用户别名"},
        ),
        migrations.AddConstraint(
            model_name="revenuecatentitlement",
            constraint=models.UniqueConstraint(fields=("user", "entitlement_identifier", "environment"), name="subscriptions_unique_rc_entitlement_snapshot"),
        ),
    ]
