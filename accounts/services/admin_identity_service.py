"""Admin-only SocialIdentity maintenance for phone/email identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from accounts.models import SocialIdentity
from accounts.services.account_identity_service import AccountIdentityService
from accounts.services.identity_scope_service import IdentityScopeService
from common.exceptions import APIError

User = get_user_model()

MANUAL_PROVIDERS = {
    SocialIdentity.Provider.PHONE,
    SocialIdentity.Provider.EMAIL,
}


@dataclass
class AdminIdentityMutationResult:
    user: Any
    provider: str
    identity_scope: str
    old_uid: str
    new_uid: str
    remaining_count: int


def normalize_manual_provider(provider: str) -> str:
    raw = (provider or "").strip().lower()
    if not raw:
        raise APIError("provider_required", code=41301, status_code=400)
    if raw not in MANUAL_PROVIDERS:
        raise APIError("unsupported_manual_provider", code=41302, status_code=400)
    return raw


def _normalize_manual_uid(*, provider: str, provider_uid: str) -> str:
    normalized = AccountIdentityService.normalize_provider_uid(provider, provider_uid)
    if provider == SocialIdentity.Provider.EMAIL:
        local, sep, domain = normalized.partition("@")
        if not sep or not local or "." not in domain:
            raise APIError("identity_format_invalid", code=41305, status_code=400)
    return normalized


def _lock_user(user_id: int):
    try:
        return User.objects.select_for_update().get(pk=user_id)
    except User.DoesNotExist as exc:
        raise APIError("user_not_found", code=40401, status_code=404) from exc


def _lock_identity(*, user, identity_id: int) -> SocialIdentity:
    try:
        return SocialIdentity.objects.select_for_update().get(pk=identity_id, user=user)
    except SocialIdentity.DoesNotExist as exc:
        raise APIError("auth_identity_not_found", code=40402, status_code=404) from exc


def _raise_already_bound(*, provider: str, provider_uid: str) -> None:
    raise APIError(
        "identity_already_bound",
        code=40941,
        status_code=409,
        details={
            "provider": provider,
            "masked_target": AccountIdentityService.mask_identity(provider, provider_uid),
        },
    )


def _sync_email(*, user, email: str) -> None:
    AccountIdentityService._sync_user_email(user=user, email=email)


def _clear_user_email(*, user) -> None:
    if (user.email or "") == "":
        return
    user.email = ""
    user.save(update_fields=["email"])


def _remaining_count(user) -> int:
    return SocialIdentity.objects.filter(user=user).count()


@transaction.atomic
def admin_create_identity(*, user_id: int, provider: str, provider_uid: str, bundle_id: str) -> AdminIdentityMutationResult:
    user = _lock_user(user_id)
    provider = normalize_manual_provider(provider)
    scope = IdentityScopeService.resolve_admin_scope(bundle_id)
    normalized_uid = _normalize_manual_uid(provider=provider, provider_uid=provider_uid)

    existing_own = (
        SocialIdentity.objects.select_for_update()
        .filter(user=user, bundle_id=scope, provider=provider)
        .first()
    )
    if existing_own is not None:
        _raise_already_bound(provider=provider, provider_uid=normalized_uid)

    existing = AccountIdentityService.get_existing_identity(
        identity_scope=scope,
        provider=provider,
        provider_uid=normalized_uid,
        for_update=True,
    )
    if existing is not None:
        _raise_already_bound(provider=provider, provider_uid=normalized_uid)

    try:
        SocialIdentity.objects.create(
            user=user,
            provider=provider,
            provider_uid=normalized_uid,
            bundle_id=scope,
        )
    except IntegrityError:
        _raise_already_bound(provider=provider, provider_uid=normalized_uid)

    if provider == SocialIdentity.Provider.EMAIL:
        _sync_email(user=user, email=normalized_uid)

    return AdminIdentityMutationResult(
        user=user,
        provider=provider,
        identity_scope=scope,
        old_uid="",
        new_uid=normalized_uid,
        remaining_count=_remaining_count(user),
    )


@transaction.atomic
def admin_update_identity(*, user_id: int, identity_id: int, provider_uid: str) -> AdminIdentityMutationResult:
    user = _lock_user(user_id)
    identity = _lock_identity(user=user, identity_id=identity_id)
    if identity.provider not in MANUAL_PROVIDERS:
        raise APIError("unsupported_manual_provider", code=41302, status_code=400)

    old_uid = identity.provider_uid
    new_uid = _normalize_manual_uid(provider=identity.provider, provider_uid=provider_uid)

    if new_uid != old_uid:
        conflict = AccountIdentityService.get_existing_identity(
            identity_scope=identity.bundle_id,
            provider=identity.provider,
            provider_uid=new_uid,
            for_update=True,
        )
        if conflict is not None and conflict.pk != identity.pk:
            _raise_already_bound(provider=identity.provider, provider_uid=new_uid)
        identity.provider_uid = new_uid
        try:
            identity.save(update_fields=["provider_uid", "updated_at"])
        except IntegrityError:
            _raise_already_bound(provider=identity.provider, provider_uid=new_uid)

    if identity.provider == SocialIdentity.Provider.EMAIL:
        _sync_email(user=user, email=new_uid)

    return AdminIdentityMutationResult(
        user=user,
        provider=identity.provider,
        identity_scope=identity.bundle_id,
        old_uid=old_uid,
        new_uid=new_uid,
        remaining_count=_remaining_count(user),
    )


@transaction.atomic
def admin_delete_identity(*, user_id: int, identity_id: int) -> AdminIdentityMutationResult:
    user = _lock_user(user_id)
    identity = _lock_identity(user=user, identity_id=identity_id)
    if identity.provider not in MANUAL_PROVIDERS:
        raise APIError("unsupported_manual_provider", code=41302, status_code=400)

    old_uid = identity.provider_uid
    provider = identity.provider
    scope = identity.bundle_id
    remaining_before = SocialIdentity.objects.filter(user=user).count()
    identity.delete()

    if provider == SocialIdentity.Provider.EMAIL:
        _clear_user_email(user=user)

    return AdminIdentityMutationResult(
        user=user,
        provider=provider,
        identity_scope=scope,
        old_uid=old_uid,
        new_uid="",
        remaining_count=max(remaining_before - 1, 0),
    )
