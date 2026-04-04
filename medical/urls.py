from django.urls import include, path
from rest_framework.routers import DefaultRouter

from medical.views import (
    ExaminationReportViewSet,
    HealthMetricRecordViewSet,
    MedicalCaseViewSet,
    MedicalReportViewSet,
    MedicalSyncBootstrapView,
    MedicalSyncUploadView,
    MemberViewSet,
    PrescriptionViewSet,
)

router = DefaultRouter()
router.register("members", MemberViewSet, basename="medical-members")
router.register("cases", MedicalCaseViewSet, basename="medical-cases")
router.register("examination-reports", ExaminationReportViewSet, basename="medical-examination-reports")
router.register("medical-reports", MedicalReportViewSet, basename="medical-medical-reports")
router.register("prescriptions", PrescriptionViewSet, basename="medical-prescriptions")
router.register("health-metrics", HealthMetricRecordViewSet, basename="medical-health-metrics")

urlpatterns = [
    path("", include(router.urls)),
    path("sync/bootstrap/", MedicalSyncBootstrapView.as_view(), name="medical-sync-bootstrap"),
    path("sync/upload/", MedicalSyncUploadView.as_view(), name="medical-sync-upload"),
]
