from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

import jwt
from django.conf import settings
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import error_response, success_response


class AIChatBridgeTokenRequestSerializer(serializers.Serializer):
    client = serializers.ChoiceField(choices=["ios"])
    device_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    app_bundle = serializers.CharField(max_length=128)
    purpose = serializers.ChoiceField(choices=["deeptutor_ai_chat"])


class AIChatBridgeTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AIChatBridgeTokenRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                msg="invalid_request",
                code=40001,
                status_code=400,
            )

        data = serializer.validated_data
        allowed_bundles = getattr(settings, "AI_CHAT_ALLOWED_BUNDLES", [])
        if allowed_bundles and data["app_bundle"] not in allowed_bundles:
            return error_response(
                msg="forbidden_bundle",
                code=40301,
                status_code=403,
            )

        bridge_secret = (getattr(settings, "DEEPTUTOR_BRIDGE_JWT_SECRET", "") or "").strip()
        if not bridge_secret:
            return error_response(
                msg="bridge_token_sign_failed",
                code=50001,
                status_code=500,
            )

        http_base_url = (getattr(settings, "DEEPTUTOR_HTTP_BASE_URL", "") or "").strip()
        ws_url = (getattr(settings, "DEEPTUTOR_WS_URL", "") or "").strip()
        if not http_base_url or not ws_url:
            return error_response(
                msg="bridge_token_sign_failed",
                code=50001,
                status_code=500,
            )

        ttl_minutes = int(getattr(settings, "AI_CHAT_BRIDGE_TOKEN_TTL_MINUTES", 10))
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=ttl_minutes)

        payload = {
            "token_type": "deeptutor_bridge",
            "purpose": "deeptutor_ai_chat",
            "iss": "SparkService",
            "aud": "DeepTutorSerevr",
            "sub": str(request.user.id),
            "user_id": str(request.user.id),
            "client": data["client"],
            "device_id": data.get("device_id") or "",
            "bundle_id": data["app_bundle"],
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": uuid.uuid4().hex,
        }

        try:
            token = jwt.encode(payload, bridge_secret, algorithm="HS256")
        except Exception:
            return error_response(
                msg="bridge_token_sign_failed",
                code=50001,
                status_code=500,
            )

        if isinstance(token, bytes):
            token = token.decode("utf-8")

        response_data = {
            "token": token,
            "expires_at": int(expires_at.timestamp()),
            "deeptutor_ws_url": ws_url,
            "deeptutor_http_base_url": http_base_url,
        }

        profile_id = (getattr(settings, "DEEPTUTOR_LLM_PROFILE_ID", "") or "").strip()
        model_id = (getattr(settings, "DEEPTUTOR_LLM_MODEL_ID", "") or "").strip()
        if profile_id and model_id:
            response_data["llm_selection"] = {
                "profile_id": profile_id,
                "model_id": model_id,
            }

        return success_response(
            response_data,
            msg="ok",
            code=0,
        )
