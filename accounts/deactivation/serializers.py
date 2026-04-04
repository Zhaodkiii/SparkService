from rest_framework import serializers


class AccountDeactivationRequestSerializer(serializers.Serializer):
    # Optional metadata for audit / future expansion.
    reason = serializers.CharField(max_length=256, required=False, allow_blank=True)

