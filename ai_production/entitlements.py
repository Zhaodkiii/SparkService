from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from billing.identity import identity_for
from billing.membership import is_active, refresh
from billing.models import BillingIdentity, MembershipSnapshot


def production_identities():
    return BillingIdentity.objects.filter(
        rc_project_id=settings.REVENUECAT_PROJECT_ID, wallet_domain="production",
    )


def identity_for_account(user):
    return production_identities().filter(account=user).first()


def prepare_identity(request):
    # A sandbox identity can only be selected using a verified billing session.
    identity = (identity_for(request) if request.headers.get("X-Billing-Session")
                else identity_for_account(request.user))
    if identity and identity.state == "active":
        refresh(identity)
    return identity


def entitlement(identity, now=None, *, lock=False):
    now = now or timezone.now()
    if identity is None:
        return "free", None
    rows = MembershipSnapshot.objects
    if lock:
        identity = BillingIdentity.objects.select_for_update().get(pk=identity.pk)
        rows = rows.select_for_update()
    row = rows.filter(identity=identity).first()
    if (identity.state != "active" or not row or row.needs_sync or not row.verified_at
            or row.verified_at < now - timedelta(hours=1)):
        return None, row
    return ("pro" if is_active(row, identity, now) else "free"), row


def filter_accounts(users, plan, now):
    identities = production_identities()
    verified = identities.filter(state="active", membershipsnapshot__needs_sync=False,
                                 membershipsnapshot__verified_at__gte=now - timedelta(hours=1))
    pro = verified.filter(
        Q(membershipsnapshot__active_until__gt=now)
        | Q(membershipsnapshot__access_granted=True, membershipsnapshot__subscription_status="in_grace_period",
            membershipsnapshot__verified_at__gt=now - timedelta(minutes=5))
    )
    if plan == "pro":
        return users.filter(pk__in=pro.values("account_id"))
    if plan == "free":
        return users.exclude(pk__in=identities.exclude(pk__in=verified.values("pk")).values("account_id")).exclude(
            pk__in=pro.values("account_id"))
    return users.filter(pk__in=identities.exclude(pk__in=verified.values("pk")).values("account_id"))
