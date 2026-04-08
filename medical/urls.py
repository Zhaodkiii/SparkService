from django.urls import include, path
from rest_framework.routers import DefaultRouter

from medical.unified_resources import UnifiedMedicalResourceViewSet
from medical.views import (
    ExaminationReportViewSet,
    FollowUpViewSet,
    HealthExamReportViewSet,
    HealthExamWorkflowSaveView,
    HealthMetricRecordViewSet,
    MemberMedicalSummaryView,
    MedicalAttachmentBatchBindView,
    MedicationTakenRecordViewSet,
    MedicationWorkflowSaveView,
    MedicationViewSet,
    MedExamDetailViewSet,
    MedicalCaseViewSet,
    MedicalCaseWorkflowSaveView,
    MedicalReportWorkflowSaveView,
    MemberViewSet,
    PrescriptionWorkflowSaveView,
    PrescriptionBatchViewSet,
    SurgeryViewSet,
    SymptomViewSet,
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
router.register("prescription-batches", PrescriptionBatchViewSet, basename="medical-prescription-batches")
router.register("medications", MedicationViewSet, basename="medical-medications")
router.register("medication-taken-records", MedicationTakenRecordViewSet, basename="medical-medication-taken-records")
router.register("health-metrics", HealthMetricRecordViewSet, basename="medical-health-metrics")
router.register("resources", UnifiedMedicalResourceViewSet, basename="medical-unified-resources")

urlpatterns = [
    path("", include(router.urls)),
    path("members/<int:member_id>/summary/", MemberMedicalSummaryView.as_view(), name="medical-member-summary"),
    path("workflows/case-documents/save/", MedicalCaseWorkflowSaveView.as_view(), name="medical-workflow-case-save"),
    path("workflows/health-exams/save/", HealthExamWorkflowSaveView.as_view(), name="medical-workflow-health-exam-save"),
    path("workflows/medical-reports/save/", MedicalReportWorkflowSaveView.as_view(), name="medical-workflow-medical-report-save"),
    path("workflows/prescriptions/save/", PrescriptionWorkflowSaveView.as_view(), name="medical-workflow-prescription-save"),
    path("workflows/medications/save/", MedicationWorkflowSaveView.as_view(), name="medical-workflow-medication-save"),
    path("workflows/attachments/batch-bind/", MedicalAttachmentBatchBindView.as_view(), name="medical-workflow-attachment-batch-bind"),
]
