from django.urls import path

from accounts.auth.views import AppleLoginView, CurrentSessionView, LogoutView, PasswordLoginView
from accounts.device.views import DeviceRegisterView
from accounts.deactivation.views import AccountDeactivationView
from accounts.identity.views import (
    AccountIdentitiesView,
    BindIdentityView,
    ChangeIdentityView,
    IdentityVerificationRequestView,
    IdentityVerificationVerifyView,
)
from accounts.otp.views import (
    EmailOTPRequestView,
    EmailOTPVerifyView,
    PhoneOTPRequestView,
    PhoneOTPVerifyView,
)

urlpatterns = [
    # Auth
    path("auth/password/login/", PasswordLoginView.as_view(), name="password_login"),
    path("auth/apple/login/", AppleLoginView.as_view(), name="apple_login"),
    path("auth/session/", CurrentSessionView.as_view(), name="auth_current_session"),
    path("auth/logout/", LogoutView.as_view(), name="auth_logout"),
    # OTP (email-first)
    path("otp/email/request/", EmailOTPRequestView.as_view(), name="email_otp_request"),
    path("otp/email/verify/", EmailOTPVerifyView.as_view(), name="email_otp_verify"),
    path("otp/phone/request/", PhoneOTPRequestView.as_view(), name="phone_otp_request"),
    path("otp/phone/verify/", PhoneOTPVerifyView.as_view(), name="phone_otp_verify"),
    # Account identity linking
    path("accounts/identities/", AccountIdentitiesView.as_view(), name="account_identities"),
    path(
        "accounts/identity-verification/request/",
        IdentityVerificationRequestView.as_view(),
        name="account_identity_verification_request",
    ),
    path(
        "accounts/identity-verification/verify/",
        IdentityVerificationVerifyView.as_view(),
        name="account_identity_verification_verify",
    ),
    path("accounts/identities/bind/", BindIdentityView.as_view(), name="account_identities_bind"),
    path("accounts/identities/change/", ChangeIdentityView.as_view(), name="account_identities_change"),
    # Trusted devices
    path("device/register/", DeviceRegisterView.as_view(), name="device_register"),
    # Deactivation (state machine + celery)
    path("deactivation/", AccountDeactivationView.as_view(), name="account_deactivation"),
]
