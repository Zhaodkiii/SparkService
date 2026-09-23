from django.db import IntegrityError, transaction

from subscriptions.models import RevenueCatCustomerAlias, RevenueCatCustomerIdentity


class RevenueCatIdentityConflict(Exception):
    pass


class RevenueCatIdentityService:
    _ALIAS_MAX_LENGTH = 255

    @staticmethod
    @transaction.atomic
    def ensure_identity(*, user) -> RevenueCatCustomerIdentity:
        expected = str(user.id)
        try:
            identity, _ = RevenueCatCustomerIdentity.objects.select_for_update().get_or_create(
                user=user,
                defaults={"app_user_id": expected},
            )
        except IntegrityError as exc:
            raise RevenueCatIdentityConflict("identity_conflict") from exc
        if identity.app_user_id != expected:
            raise RevenueCatIdentityConflict("identity_conflict")
        return identity

    @staticmethod
    @transaction.atomic
    def remember_aliases(*, identity: RevenueCatCustomerIdentity, aliases: list[str], source: str) -> None:
        for raw_alias in aliases:
            alias = str(raw_alias or "").strip()
            if not alias or len(alias) > RevenueCatIdentityService._ALIAS_MAX_LENGTH or alias == identity.app_user_id:
                continue
            row = RevenueCatCustomerAlias.objects.select_for_update().filter(alias=alias).first()
            if row and row.identity_id != identity.id:
                raise RevenueCatIdentityConflict("alias_conflict")
            if row:
                row.source = source
                row.save(update_fields=["source", "last_seen_at"])
            else:
                RevenueCatCustomerAlias.objects.create(identity=identity, alias=alias, source=source)
