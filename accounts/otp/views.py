import logging

from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework import status

from common.response import success_response
from accounts.otp.serializers import (
    EmailOTPRequestSerializer,
    EmailOTPVerifySerializer,
    PhoneOTPRequestSerializer,
    PhoneOTPVerifySerializer,
)
from accounts.services.otp_service import OTPService

flow_logger = logging.getLogger("accounts.flow")


class EmailOTPRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "auth.otp.request.begin",
            extra={"action": "auth.otp.request", "path": request.path, "method": request.method, "request_id": request_id},
        )
        serializer = EmailOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        bundle_id = serializer.validated_data.get("bundle_id", "") or ""
        device_id = serializer.validated_data.get("device_id", "") or ""
        provider_uid = serializer.validated_data.get("provider_uid", "") or ""
        scene = serializer.validated_data.get("scene", "") or "login"

        result = OTPService.request_email_otp(
            email=serializer.validated_data["email"],
            provider_uid=provider_uid,
            bundle_id=bundle_id,
            device_id=device_id,
            ip_address=ip_address,
            request_id=getattr(request, "request_id", "") or "",
            scene=scene,
        )
        flow_logger.info(
            "auth.otp.request.success",
            extra={
                "action": "auth.otp.request",
                "outcome": "success",
                "request_id": request_id,
                "otp_id": result.get("otp_id"),
            },
        )
        return success_response(result, msg="otp_sent", code=0, status_code=status.HTTP_200_OK)


class EmailOTPVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "auth.otp.verify.begin",
            extra={"action": "auth.otp.verify", "path": request.path, "method": request.method, "request_id": request_id},
        )
        serializer = EmailOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        user_agent = meta.get("HTTP_USER_AGENT", "") or ""

        bundle_id = serializer.validated_data.get("bundle_id", "") or ""
        device_id = serializer.validated_data.get("device_id", "") or ""
        device_secret = serializer.validated_data.get("device_secret", "") or ""
        device_secret = serializer.validated_data.get("device_secret", "") or ""

        result = OTPService.verify_email_otp_and_issue_tokens(
            otp_id=serializer.validated_data["otp_id"],
            email=serializer.validated_data["email"],
            code=serializer.validated_data["code"],
            request_id=getattr(request, "request_id", "") or "",
            ip_address=ip_address,
            user_agent=user_agent,
            bundle_id=bundle_id,
            device_id=device_id,
            device_secret=device_secret,
        )
        flow_logger.info(
            "auth.otp.verify.success",
            extra={
                "action": "auth.otp.verify",
                "outcome": "success",
                "request_id": request_id,
                "user_id": result.get("user_id"),
                "otp_id": result.get("otp_id"),
            },
        )
        return success_response(result, msg="otp_verified", code=0, status_code=status.HTTP_200_OK)


class PhoneOTPRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "auth.phone_otp.request.begin",
            extra={"action": "auth.phone_otp.request", "path": request.path, "method": request.method, "request_id": request_id},
        )
        serializer = PhoneOTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        bundle_id = serializer.validated_data.get("bundle_id", "") or ""
        device_id = serializer.validated_data.get("device_id", "") or ""
        provider_uid = serializer.validated_data.get("provider_uid", "") or ""
        scene = serializer.validated_data.get("scene", "") or "login"
        user_id = serializer.validated_data.get("user_id")
        actor_user_id = getattr(request.user, "id", None) if getattr(request.user, "is_authenticated", False) else None

        result = OTPService.request_phone_otp(
            phone_number=serializer.validated_data["phone_number"],
            provider_uid=provider_uid,
            bundle_id=bundle_id,
            device_id=device_id,
            ip_address=ip_address,
            request_id=request_id,
            scene=scene,
            user_id=user_id,
            actor_user_id=actor_user_id,
        )
        flow_logger.info(
            "auth.phone_otp.request.success",
            extra={
                "action": "auth.phone_otp.request",
                "outcome": "success",
                "request_id": request_id,
                "otp_id": result.get("otp_id"),
            },
        )
        return success_response(result, msg="otp_sent", code=0, status_code=status.HTTP_200_OK)


class PhoneOTPVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        flow_logger.info(
            "auth.phone_otp.verify.begin",
            extra={"action": "auth.phone_otp.verify", "path": request.path, "method": request.method, "request_id": request_id},
        )
        serializer = PhoneOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        meta = request.META
        ip_address = meta.get("HTTP_X_FORWARDED_FOR", meta.get("REMOTE_ADDR", "")) or ""
        user_agent = meta.get("HTTP_USER_AGENT", "") or ""
        bundle_id = serializer.validated_data.get("bundle_id", "") or ""
        device_id = serializer.validated_data.get("device_id", "") or ""
        device_secret = serializer.validated_data.get("device_secret", "") or ""

        result = OTPService.verify_phone_otp_and_issue_tokens(
            otp_id=serializer.validated_data["otp_id"],
            phone_number=serializer.validated_data["phone_number"],
            code=serializer.validated_data["code"],
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            bundle_id=bundle_id,
            device_id=device_id,
            device_secret=device_secret,
        )
        flow_logger.info(
            "auth.phone_otp.verify.success",
            extra={
                "action": "auth.phone_otp.verify",
                "outcome": "success",
                "request_id": request_id,
                "user_id": result.get("user_id"),
                "otp_id": result.get("otp_id"),
            },
        )
        return success_response(result, msg="otp_verified", code=0, status_code=status.HTTP_200_OK)
