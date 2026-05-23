from django.urls import include, path
from rest_framework.routers import DefaultRouter

from medical.unified_resources import UnifiedMedicalResourceViewSet
from medical.views import (
    CombinedMedicalCreateAPIView,
    ExaminationReportViewSet,
    FollowUpWorkflowCreateView,
    FollowUpViewSet,
    HealthExamReportViewSet,
    HealthExamWorkflowSaveView,
    MedicineBoxViewSet,
    MemberBindingViewSet,
    MemberCompleteDataAPI,
    MedicalAttachmentBatchBindView,
    MedicationPlanWorkflowSaveView,
    MedicationPlanViewSet,
    MedicationRecordViewSet,
    MedExamDetailViewSet,
    MedicalCaseViewSet,
    MedicalCaseWorkflowSaveView,
    MedicalReportWorkflowSaveView,
    MemberBindingRemoveView,
    MemberBindingPermissionUpdateView,
    MemberBindingRoleUpdateView,
    MemberBindingTransferOwnerView,
    MemberShareInviteAcceptView,
    MemberShareInviteCancelView,
    MemberShareInviteCreateView,
    MemberShareInviteDetailView,
    MemberShareInviteRejectView,
    MemberShareTicketAcceptAPI,
    MemberShareTicketCreateAPI,
    MemberShareTicketResolveAPI,
    MemberViewSet,
    PendingMemberInvitesView,
    PrescriptionViewSet,
    SurgeryWorkflowCreateView,
    SymptomWorkflowCreateView,
    SurgeryViewSet,
    SymptomViewSet,
    VisitWorkflowCreateView,
    VisitViewSet,
)

router = DefaultRouter()
router.register("members", MemberViewSet, basename="medical-members")
router.register("cases", MedicalCaseViewSet, basename="medical-cases")
router.register("symptoms", SymptomViewSet, basename="medical-symptoms")
router.register("visits", VisitViewSet, basename="medical-visits")
router.register("surgeries", SurgeryViewSet, basename="medical-surgeries")
router.register("follow-ups", FollowUpViewSet, basename="medical-follow-ups")
router.register("health-exam-reports", HealthExamReportViewSet, basename="medical-health-exam-reports")
router.register("examination-reports", ExaminationReportViewSet, basename="medical-examination-reports")
router.register("med-exam-details", MedExamDetailViewSet, basename="medical-med-exam-details")
router.register("medicine-boxes", MedicineBoxViewSet, basename="medical-medicine-boxes")
router.register("prescriptions", PrescriptionViewSet, basename="medical-prescriptions")
router.register("medication-plans", MedicationPlanViewSet, basename="medical-medication-plans")
router.register("medication-records", MedicationRecordViewSet, basename="medical-medication-records")
router.register("resources", UnifiedMedicalResourceViewSet, basename="medical-unified-resources")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "member-bindings/<int:pk>/",
        MemberBindingViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="medical-member-bindings-detail",
    ),
    path(
        "members/<int:member_id>/share-ticket/",
        MemberShareTicketCreateAPI.as_view(),
        name="medical-member-share-ticket",
    ),
    path(
        "member-share-ticket/resolve/",
        MemberShareTicketResolveAPI.as_view(),
        name="medical-member-share-ticket-resolve",
    ),
    path(
        "member-share-ticket/accept/",
        MemberShareTicketAcceptAPI.as_view(),
        name="medical-member-share-ticket-accept",
    ),
    path(
        "members/<int:member_id>/invites/",
        MemberShareInviteCreateView.as_view(),
        name="medical-member-share-invite-create",
    ),
    path(
        "member-invites/pending/",
        PendingMemberInvitesView.as_view(),
        name="medical-member-invites-pending",
    ),
    path(
        "member-invites/<int:invite_id>/",
        MemberShareInviteDetailView.as_view(),
        name="medical-member-invite-detail",
    ),
    path(
        "member-invites/<int:invite_id>/accept/",
        MemberShareInviteAcceptView.as_view(),
        name="medical-member-invite-accept",
    ),
    path(
        "member-invites/<int:invite_id>/reject/",
        MemberShareInviteRejectView.as_view(),
        name="medical-member-invite-reject",
    ),
    path(
        "member-invites/<int:invite_id>/cancel/",
        MemberShareInviteCancelView.as_view(),
        name="medical-member-invite-cancel",
    ),
    path(
        "member-bindings/<int:pk>/role/",
        MemberBindingRoleUpdateView.as_view(),
        name="medical-member-binding-role",
    ),
    path(
        "member-bindings/<int:pk>/permission/",
        MemberBindingPermissionUpdateView.as_view(),
        name="medical-member-binding-permission",
    ),
    path(
        "member-bindings/<int:pk>/remove/",
        MemberBindingRemoveView.as_view(),
        name="medical-member-binding-remove",
    ),
    path(
        "member-bindings/<int:pk>/transfer-owner/",
        MemberBindingTransferOwnerView.as_view(),
        name="medical-member-binding-transfer-owner",
    ),
    path("members/<int:member_id>/complete-data/", MemberCompleteDataAPI.as_view(), name="medical-member-complete-data"),
    path("workflows/case-documents/save/", MedicalCaseWorkflowSaveView.as_view(), name="medical-workflow-case-save"),
    path("workflows/health-exams/save/", HealthExamWorkflowSaveView.as_view(), name="medical-workflow-health-exam-save"),
    path("workflows/medical-reports/create/", MedicalReportWorkflowSaveView.as_view(), name="medical-workflow-medical-report-create"),
    path("workflows/medication-plans/save/", MedicationPlanWorkflowSaveView.as_view(), name="medical-workflow-medication-plan-save"),
    path("workflows/symptoms/create/", SymptomWorkflowCreateView.as_view(), name="medical-workflow-symptom-create"),
    path("workflows/visits/create/", VisitWorkflowCreateView.as_view(), name="medical-workflow-visit-create"),
    path("workflows/surgeries/create/", SurgeryWorkflowCreateView.as_view(), name="medical-workflow-surgery-create"),
    path("workflows/follow-ups/create/", FollowUpWorkflowCreateView.as_view(), name="medical-workflow-follow-up-create"),
    path("workflows/attachments/batch-bind/", MedicalAttachmentBatchBindView.as_view(), name="medical-workflow-attachment-batch-bind"),
    # 新增组合创建 API（一次性创建完整医疗记录）
    path("combined-create/", CombinedMedicalCreateAPIView.as_view(), name="medical-combined-create"),
]
