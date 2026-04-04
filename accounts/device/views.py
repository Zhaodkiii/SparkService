from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework import status

from common.response import success_response
from accounts.device.serializers import DeviceRegisterSerializer
from accounts.services.device_service import DeviceService


class DeviceRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeviceRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        result = DeviceService.register_trusted_device(
            user=request.user,
            device_id=data["device_id"],
            bundle_id=data.get("bundle_id", "") or "",
            nickname=data.get("nickname", "") or "",
            request_id=getattr(request, "request_id", "") or "",
        )
        return success_response(result, msg="device_registered", code=0, status_code=status.HTTP_200_OK)

