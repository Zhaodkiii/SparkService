from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="revenuecatwebhookevent",
            name="process_status",
            field=models.CharField(choices=[("received", "已接收"), ("processing", "处理中"), ("processed", "已处理"), ("unmatched", "待匹配"), ("retryable", "待重试"), ("ownership_conflict", "归属冲突"), ("failed", "失败")], db_index=True, default="received", max_length=32),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="billing_status",
            field=models.CharField(blank=True, db_index=True, default="normal", max_length=32),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="unsubscribe_detected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="billing_issue_detected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="grace_period_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="revoked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="pending_product_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="product_change_effective_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="ownership_type",
            field=models.CharField(blank=True, default="unknown", max_length=32),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="last_event_type",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="revenuecatentitlement",
            name="last_event_timestamp_ms",
            field=models.BigIntegerField(db_index=True, default=0),
        ),
        migrations.CreateModel(
            name="RevenueCatSubscriptionOwnership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("store", models.CharField(max_length=32)),
                ("environment", models.CharField(db_index=True, max_length=16)),
                ("original_transaction_id", models.CharField(max_length=255)),
                ("state", models.CharField(choices=[("active", "有效归属"), ("tombstone", "注销墓碑")], db_index=True, default="active", max_length=16)),
                ("owner_account_fingerprint", models.CharField(max_length=128)),
                ("first_product_id", models.CharField(blank=True, default="", max_length=255)),
                ("first_bound_at", models.DateTimeField()),
                ("last_verified_at", models.DateTimeField()),
                ("tombstoned_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="revenuecat_subscription_ownerships", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "RevenueCat 订阅所有权",
                "verbose_name_plural": "RevenueCat 订阅所有权",
                "indexes": [
                    models.Index(fields=["user", "environment", "state"], name="subscriptio_owner_user_env_idx"),
                    models.Index(fields=["state", "tombstoned_at"], name="subscriptio_owner_state_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="revenuecatsubscriptionownership",
            constraint=models.UniqueConstraint(fields=("store", "environment", "original_transaction_id"), name="subscriptions_unique_rc_transaction_owner"),
        ),
        migrations.CreateModel(
            name="RevenueCatOwnershipConflictEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("trigger", models.CharField(max_length=32)),
                ("store", models.CharField(blank=True, default="", max_length=32)),
                ("environment", models.CharField(blank=True, default="", max_length=16)),
                ("transaction_suffix", models.CharField(blank=True, default="", max_length=12)),
                ("request_id", models.CharField(blank=True, default="", max_length=64)),
                ("occurred_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("attempted_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("ownership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="conflicts", to="subscriptions.revenuecatsubscriptionownership")),
            ],
            options={
                "verbose_name": "RevenueCat 订阅归属冲突",
                "verbose_name_plural": "RevenueCat 订阅归属冲突",
                "indexes": [models.Index(fields=["attempted_user", "occurred_at"], name="subscriptio_conflict_user_idx")],
            },
        ),
        migrations.CreateModel(
            name="RevenueCatSyncRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idempotency_key", models.CharField(max_length=128)),
                ("status", models.CharField(default="processing", max_length=16)),
                ("response_payload", models.JSONField(blank=True, null=True)),
                ("response_status", models.PositiveSmallIntegerField(default=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revenuecat_sync_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["user", "created_at"], name="subscriptio_sync_user_idx")],
            },
        ),
        migrations.AddConstraint(
            model_name="revenuecatsyncrequest",
            constraint=models.UniqueConstraint(fields=("user", "idempotency_key"), name="subscriptions_unique_sync_request_key"),
        ),
    ]
