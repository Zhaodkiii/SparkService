from django.urls import include, path
from rest_framework.routers import DefaultRouter

from medical.views import (
    ExaminationReportViewSet,
    FollowUpViewSet,
    HealthExamReportViewSet,
    HealthMetricRecordViewSet,
    MedicationTakenRecordViewSet,
    MedicationViewSet,
    MedExamDetailViewSet,
    MedicalCaseViewSet,
    MedicalReportViewSet,
    MedicalSyncBootstrapView,
    MedicalSyncUploadView,
    MemberViewSet,
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
router.register("medical-reports", MedicalReportViewSet, basename="medical-medical-reports")
router.register("prescription-batches", PrescriptionBatchViewSet, basename="medical-prescription-batches")
router.register("medications", MedicationViewSet, basename="medical-medications")
router.register("medication-taken-records", MedicationTakenRecordViewSet, basename="medical-medication-taken-records")
router.register("health-metrics", HealthMetricRecordViewSet, basename="medical-health-metrics")

urlpatterns = [
    path("", include(router.urls)),
    path("sync/bootstrap/", MedicalSyncBootstrapView.as_view(), name="medical-sync-bootstrap"),
    path("sync/upload/", MedicalSyncUploadView.as_view(), name="medical-sync-upload"),
]
