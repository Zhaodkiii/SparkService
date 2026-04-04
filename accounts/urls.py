from django.urls import path

from accounts.auth.views import AppleLoginView, PasswordLoginView
from accounts.device.views import DeviceRegisterView
from accounts.deactivation.views import AccountDeactivationView
from accounts.otp.views import (
    EmailOTPRequestView,
    EmailOTPVerifyView,
)

urlpatterns = [
    # Auth
    path("auth/password/login/", PasswordLoginView.as_view(), name="password_login"),
    path("auth/apple/login/", AppleLoginView.as_view(), name="apple_login"),
    # OTP (email-first)
    path("otp/email/request/", EmailOTPRequestView.as_view(), name="email_otp_request"),
    path("otp/email/verify/", EmailOTPVerifyView.as_view(), name="email_otp_verify"),
    # Trusted devices
    path("device/register/", DeviceRegisterView.as_view(), name="device_register"),
    # Deactivation (state machine + celery)
    path("deactivation/", AccountDeactivationView.as_view(), name="account_deactivation"),
]
