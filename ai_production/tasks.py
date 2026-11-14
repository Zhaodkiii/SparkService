from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import ProductionCall
from .services import expire_account_calls


@shared_task
def expire_usage():
    accounts = ProductionCall.objects.filter(accounting_state="pending", usage_due_at__lte=timezone.now())
    users = get_user_model().objects.filter(pk__in=accounts.values("task__account_id"))
    for user in users.iterator():
        expire_account_calls(user)
