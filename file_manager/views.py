import hashlib
import mimetypes
import os

from django.db.models import Q
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.http_cache import build_etag, normalize_etag
from common.response import error_response, success_response
from file_manager.models import ManagedFile
from file_manager.serializers import (
    ManagedFileBusinessUpdateSerializer,
    ManagedFileRecordSerializer,
    ManagedFileUploadSerializer,
)


class ManagedFileListView(APIView):
    permission_classes = [IsAuthenticated]
    etag_max_age = 120

    def get(self, request):
        queryset = ManagedFile.objects.filter(user=request.user, is_deleted=False)

        business_type = request.query_params.get("business_type", "")
        business_id = request.query_params.get("business_id", "")
        is_public = request.query_params.get("is_public")

        if business_type:
            queryset = queryset.filter(business_type=business_type)
        if business_id:
            queryset = queryset.filter(business_id=business_id)
        if is_public is not None:
            queryset = queryset.filter(is_public=self._to_bool(is_public))

        etag = build_etag(
            {
                "path": request.path,
                "query": request.query_params.dict(),
                "user_id": request.user.id,
                "records": list(queryset.values_list("id", "updated_at")),
            }
        )
        incoming = normalize_etag(request.headers.get("If-None-Match"))
        if incoming and incoming == normalize_etag(etag):
            response = success_response(None, msg="not_modified", code=0, status_code=status.HTTP_304_NOT_MODIFIED)
            response.content = b""
            return response

        serializer = ManagedFileRecordSerializer(queryset, many=True)
        response = success_response(serializer.data, msg="success", code=0, status_code=status.HTTP_200_OK)
        response["ETag"] = etag
        response["Cache-Control"] = f"private, max-age={self.etag_max_age}"
        return response

    def _to_bool(self, value):
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "y", "on"}


class ManagedFileUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payload = self._normalize_payload(request.data)
        serializer = ManagedFileUploadSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        uploaded_file = data["file"]
        expected_md5 = data.get("file_md5", "").strip().lower()

        actual_md5 = self._compute_md5(uploaded_file)
        if expected_md5 and expected_md5 != actual_md5:
            return error_response(msg="file_md5_mismatch", code=4001, status_code=status.HTTP_400_BAD_REQUEST)

        original_name = uploaded_file.name or f"file-{actual_md5[:8]}"
        ext = os.path.splitext(original_name)[1].lstrip(".").lower()
        mime_type = uploaded_file.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"

        file_record = ManagedFile.objects.create(
            user=request.user,
            file=uploaded_file,
            original_name=original_name,
            file_ext=ext,
            mime_type=mime_type,
            file_size=getattr(uploaded_file, "size", 0),
            file_md5=actual_md5,
            is_public=data.get("is_public", False),
            business_type=data["business_type"],
            business_id=data.get("business_id", ""),
        )

        return success_response(ManagedFileRecordSerializer(file_record).data, msg="created", code=0, status_code=status.HTTP_201_CREATED)

    def _compute_md5(self, uploaded_file):
        digest = hashlib.md5()
        for chunk in uploaded_file.chunks():
            digest.update(chunk)
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        return digest.hexdigest()

    def _normalize_payload(self, payload):
        data = payload.copy()
        value = data.get("is_public")
        if value is not None and isinstance(value, str):
            data["is_public"] = value.lower() in {"1", "true", "yes", "y", "on"}
        return data


class ManagedFileBusinessUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = ManagedFileBusinessUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        file_record = ManagedFile.objects.filter(id=data["file_id"], user=request.user, is_deleted=False).first()
        if not file_record:
            return error_response(msg="file_not_found", code=4040, status_code=status.HTTP_404_NOT_FOUND)

        file_record.business_type = data["business_type"]
        file_record.business_id = data.get("business_id", "")
        file_record.save(update_fields=["business_type", "business_id", "updated_at"])

        return success_response(ManagedFileRecordSerializer(file_record).data, msg="updated", code=0, status_code=status.HTTP_200_OK)


class ManagedFileDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, file_id):
        file_record = (
            ManagedFile.objects.filter(id=file_id, is_deleted=False)
            .filter(Q(user=request.user) | Q(is_public=True))
            .first()
        )
        if not file_record:
            raise Http404("file not found")

        if not file_record.file:
            return error_response(msg="file_missing", code=4041, status_code=status.HTTP_404_NOT_FOUND)

        response = FileResponse(file_record.file.open("rb"), as_attachment=True, filename=file_record.original_name)
        response["Content-Type"] = file_record.mime_type or "application/octet-stream"
        response["Cache-Control"] = "private, no-store"
        return response


class ManagedFileDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, file_id):
        file_record = ManagedFile.objects.filter(id=file_id, user=request.user, is_deleted=False).first()
        if not file_record:
            return error_response(msg="file_not_found", code=4040, status_code=status.HTTP_404_NOT_FOUND)

        file_record.soft_delete()
        return success_response({"id": file_record.id}, msg="deleted", code=0, status_code=status.HTTP_200_OK)
