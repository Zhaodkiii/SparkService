import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from accounts.identity.serializers import (
    BindIdentitySerializer,
    ChangeIdentitySerializer,
    IdentityListQuerySerializer,
    IdentityVerificationRequestSerializer,
    IdentityVerificationVerifySerializer,
)
from accounts.services.account_identity_service import AccountIdentityService
from common.response import success_response

flow_logger = logging.getLogger("accounts.flow")


class AccountIdentitiesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        request_id = getattr(request, "request_id", "") or ""
        serializer = IdentityListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        bundle_id = serializer.validated_data.get("bundle_id") or request.headers.get("X-Bundle-Id", "")
        flow_logger.info(
            "account.identity.list.begin",
            extra={
                "action": "account.identity.list",
                "request_id": request_id,
                "user_id": request.user.id,
                "bundle_id": bundle_id,
            },
        )
        data = AccountIdentityService.list_identities(user=request.user, bundle_id=bundle_id)
        return success_response(data, msg="ok", code=0, status_code=status.HTTP_200_OK)


class IdentityVerificationRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        serializer = IdentityVerificationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = AccountIdentityService.request_verification(
            user=request.user,
            provider=data["provider"],
            purpose=data["purpose"],
            bundle_id=data["bundle_id"],
            device_id=data.get("device_id", ""),
            ip_address=request.META.get("REMOTE_ADDR", "") or "",
            request_id=request_id,
        )
        msg = "otp_sent" if "otp_id" in result else "ready"
        return success_response(result, msg=msg, code=0, status_code=status.HTTP_200_OK)


class IdentityVerificationVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        serializer = IdentityVerificationVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = AccountIdentityService.verify_and_issue_ticket(
            user=request.user,
            provider=data["provider"],
            purpose=data["purpose"],
            bundle_id=data["bundle_id"],
            device_id=data.get("device_id", ""),
            request_id=request_id,
            otp_id=data.get("otp_id", ""),
            code=data.get("code", ""),
            identity_token=data.get("identity_token", ""),
            authorization_code=data.get("authorization_code", ""),
            user_identifier=data.get("user_identifier", ""),
        )
        return success_response(result, msg="verified", code=0, status_code=status.HTTP_200_OK)


class BindIdentityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        serializer = BindIdentitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = AccountIdentityService.bind_identity(
            user=request.user,
            provider=data["provider"],
            verification_ticket=data["verification_ticket"],
            bundle_id=data["bundle_id"],
            device_id=data.get("device_id", ""),
            request_id=request_id,
            target=data.get("target", ""),
            otp_id=data.get("otp_id", ""),
            code=data.get("code", ""),
            identity_token=data.get("identity_token", ""),
            authorization_code=data.get("authorization_code", ""),
            user_identifier=data.get("user_identifier", ""),
        )
        return success_response(result, msg="bound", code=0, status_code=status.HTTP_200_OK)


class ChangeIdentityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request_id = getattr(request, "request_id", "") or ""
        serializer = ChangeIdentitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = AccountIdentityService.change_identity(
            user=request.user,
            provider=data["provider"],
            verification_ticket=data["verification_ticket"],
            bundle_id=data["bundle_id"],
            device_id=data.get("device_id", ""),
            request_id=request_id,
            new_target=data.get("new_target", ""),
            new_otp_id=data.get("new_otp_id", ""),
            new_code=data.get("new_code", ""),
        )
        return success_response(result, msg="changed", code=0, status_code=status.HTTP_200_OK)
