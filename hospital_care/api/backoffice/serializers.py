from rest_framework import serializers

from hospital_care.models import Hospital, HospitalDepartment, HospitalStaffMembership


class HospitalCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=128)
    short_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
    grade = serializers.CharField(max_length=32, required=False, allow_blank=True)
    logo_file_id = serializers.IntegerField(required=False, allow_null=True)
    province_code = serializers.CharField(max_length=16)
    city_code = serializers.CharField(max_length=16)
    district_code = serializers.CharField(max_length=16, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255)
    service_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    emergency_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    website_url = serializers.CharField(max_length=512, required=False, allow_blank=True)
    introduction = serializers.CharField(required=False, allow_blank=True)
    registration_redirect_url = serializers.CharField(max_length=512, required=False, allow_blank=True)
    service_mode = serializers.ChoiceField(choices=Hospital.ServiceMode.choices, default=Hospital.ServiceMode.DEMO)


class HospitalUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128, required=False)
    short_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
    grade = serializers.CharField(max_length=32, required=False, allow_blank=True)
    logo_file_id = serializers.IntegerField(required=False, allow_null=True)
    province_code = serializers.CharField(max_length=16, required=False)
    city_code = serializers.CharField(max_length=16, required=False)
    district_code = serializers.CharField(max_length=16, required=False, allow_blank=True)
    address = serializers.CharField(max_length=255, required=False)
    service_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    emergency_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    website_url = serializers.CharField(max_length=512, required=False, allow_blank=True)
    introduction = serializers.CharField(required=False, allow_blank=True)
    registration_redirect_url = serializers.CharField(max_length=512, required=False, allow_blank=True)
    service_mode = serializers.ChoiceField(choices=Hospital.ServiceMode.choices, required=False)
    version = serializers.IntegerField()


class HospitalVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True)


class DepartmentCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=128)
    short_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    sort_order = serializers.IntegerField(required=False, default=0)
    status = serializers.ChoiceField(choices=HospitalDepartment.Status.choices, required=False)


class DepartmentUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128, required=False)
    short_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    sort_order = serializers.IntegerField(required=False)
    status = serializers.ChoiceField(choices=HospitalDepartment.Status.choices, required=False)


class StaffCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=HospitalStaffMembership.Role.choices)
    employee_no = serializers.CharField(max_length=64, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=HospitalStaffMembership.Status.choices, required=False)
    display_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
    title = serializers.CharField(max_length=64, required=False, allow_blank=True)
    specialties = serializers.ListField(child=serializers.CharField(), required=False)
    introduction = serializers.CharField(required=False, allow_blank=True)


class StaffUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=HospitalStaffMembership.Role.choices, required=False)
    employee_no = serializers.CharField(max_length=64, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=HospitalStaffMembership.Status.choices, required=False)
    display_name = serializers.CharField(max_length=64, required=False, allow_blank=True)
    title = serializers.CharField(max_length=64, required=False, allow_blank=True)


class DoctorUpdateSerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=64, required=False)
    title = serializers.CharField(max_length=64, required=False, allow_blank=True)
    specialties = serializers.ListField(child=serializers.CharField(), required=False)
    introduction = serializers.CharField(required=False, allow_blank=True)
    license_status = serializers.CharField(required=False)
    profile_status = serializers.CharField(required=False)
    avatar_file_id = serializers.IntegerField(required=False, allow_null=True)
    primary_department_id = serializers.UUIDField(required=False)


class AgentReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["publish", "reject", "disable"])
    version = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True)


class AgentBindingSerializer(serializers.Serializer):
    model = serializers.CharField(max_length=128, required=False)
    display_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    temperature = serializers.FloatField(required=False)
    max_tokens = serializers.IntegerField(required=False)
    system_provision = serializers.CharField(required=False, allow_blank=True)
    brief_description = serializers.CharField(required=False, allow_blank=True)
    ai_tool_scenarios = serializers.ListField(child=serializers.CharField(), required=False)
    server_tool_scenarios = serializers.ListField(child=serializers.CharField(), required=False)
    related_task_codes = serializers.ListField(child=serializers.CharField(), required=False)
    updated_at = serializers.CharField(required=False, allow_blank=True)


class AgentKnowledgeItemSerializer(serializers.Serializer):
    profile_id = serializers.UUIDField()


class AgentCreateSerializer(serializers.Serializer):
    doctor_id = serializers.UUIDField()
    department_id = serializers.UUIDField()
    name = serializers.CharField(max_length=128)
    public_summary = serializers.CharField(required=False, allow_blank=True)
    greeting = serializers.CharField(required=False, allow_blank=True)
    service_boundary = serializers.CharField(required=False, allow_blank=True)
    binding = AgentBindingSerializer()
    knowledge_bases = AgentKnowledgeItemSerializer(many=True, required=False)

    def validate_binding(self, value):
        if not (value.get("model") or "").strip():
            raise serializers.ValidationError("model is required")
        return value


class AgentUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    department_id = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=128, required=False)
    public_summary = serializers.CharField(required=False, allow_blank=True)
    greeting = serializers.CharField(required=False, allow_blank=True)
    service_boundary = serializers.CharField(required=False, allow_blank=True)
    binding = AgentBindingSerializer(required=False)
    knowledge_bases = AgentKnowledgeItemSerializer(many=True, required=False)


class KnowledgeBaseCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(required=False, allow_blank=True)
    department_ids = serializers.ListField(child=serializers.UUIDField(), required=False)


class KnowledgeBaseUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    name = serializers.CharField(max_length=128, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    department_ids = serializers.ListField(child=serializers.UUIDField(), required=False)


class KnowledgeVersionSerializer(serializers.Serializer):
    version = serializers.IntegerField()


class KnowledgeDocumentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    content = serializers.CharField(allow_blank=True)
    version = serializers.IntegerField()


class KnowledgeDocumentUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, required=False)
    content = serializers.CharField(required=False, allow_blank=True)
    revision = serializers.IntegerField()


class KnowledgeDocumentDeleteSerializer(serializers.Serializer):
    revision = serializers.IntegerField()


class KnowledgeVectorBuildSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    embedding_binding_id = serializers.IntegerField()
