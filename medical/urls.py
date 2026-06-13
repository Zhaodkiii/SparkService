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
    FamilyMedicineCabinetSummaryAPI,
    MedicineBoxViewSet,
    MemberBindingViewSet,
    MemberCompleteDataAPI,
    MedicalAttachmentBatchBindView,
    MedicationPlanWorkflowSaveView,
    PrescriptionBatchWorkflowSaveView,
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
    path("", include(router.urls)),  # ViewSet：成员/病例/药箱/处方/用药计划等资源 CRUD 与统一 resources 入口
    path("member-bindings/<int:pk>/", MemberBindingViewSet.as_view({"patch": "partial_update", "delete": "destroy"}), name="medical-member-bindings-detail"),  # 更新或删除成员绑定
    path("members/<int:member_id>/share-ticket/", MemberShareTicketCreateAPI.as_view(), name="medical-member-share-ticket"),  # 生成成员分享票据（二维码/附近分享）
    path("member-share-ticket/resolve/", MemberShareTicketResolveAPI.as_view(), name="medical-member-share-ticket-resolve"),  # 解析分享票据预览
    path("member-share-ticket/accept/", MemberShareTicketAcceptAPI.as_view(), name="medical-member-share-ticket-accept"),  # 接受分享票据建立绑定
    path("members/<int:member_id>/invites/", MemberShareInviteCreateView.as_view(), name="medical-member-share-invite-create"),  # 创建成员分享邀请
    path("member-invites/pending/", PendingMemberInvitesView.as_view(), name="medical-member-invites-pending"),  # 当前用户待处理邀请列表
    path("member-invites/<int:invite_id>/", MemberShareInviteDetailView.as_view(), name="medical-member-invite-detail"),  # 邀请详情
    path("member-invites/<int:invite_id>/accept/", MemberShareInviteAcceptView.as_view(), name="medical-member-invite-accept"),  # 接受邀请
    path("member-invites/<int:invite_id>/reject/", MemberShareInviteRejectView.as_view(), name="medical-member-invite-reject"),  # 拒绝邀请
    path("member-invites/<int:invite_id>/cancel/", MemberShareInviteCancelView.as_view(), name="medical-member-invite-cancel"),  # 取消邀请
    path("member-bindings/<int:pk>/role/", MemberBindingRoleUpdateView.as_view(), name="medical-member-binding-role"),  # 修改绑定角色
    path("member-bindings/<int:pk>/permission/", MemberBindingPermissionUpdateView.as_view(), name="medical-member-binding-permission"),  # 修改绑定权限档位
    path("member-bindings/<int:pk>/remove/", MemberBindingRemoveView.as_view(), name="medical-member-binding-remove"),  # 移除他人绑定（管理员）
    path("member-bindings/<int:pk>/transfer-owner/", MemberBindingTransferOwnerView.as_view(), name="medical-member-binding-transfer-owner"),  # 转移成员 Owner
    path("members/<int:member_id>/complete-data/", MemberCompleteDataAPI.as_view(), name="medical-member-complete-data"),  # 成员医疗数据汇总（首页/列表快照）
    path("medicine-cabinet/summary/", FamilyMedicineCabinetSummaryAPI.as_view(), name="medical-medicine-cabinet-summary"),  # 家庭药箱汇总（按入口成员推导创建者范围）
    path("workflows/case-documents/save/", MedicalCaseWorkflowSaveView.as_view(), name="medical-workflow-case-save"),  # 工作流：保存病例文档
    path("workflows/health-exams/save/", HealthExamWorkflowSaveView.as_view(), name="medical-workflow-health-exam-save"),  # 工作流：保存体检报告
    path("workflows/medical-reports/create/", MedicalReportWorkflowSaveView.as_view(), name="medical-workflow-medical-report-create"),  # 工作流：创建检查/检验报告
    path("workflows/medication-plans/save/", MedicationPlanWorkflowSaveView.as_view(), name="medical-workflow-medication-plan-save"),  # 工作流：保存用药计划（可含药箱）
    path("workflows/prescriptions/batch-save/", PrescriptionBatchWorkflowSaveView.as_view(), name="medical-workflow-prescription-batch-save"),  # 工作流：批量保存处方（不创建病历）
    path("workflows/symptoms/create/", SymptomWorkflowCreateView.as_view(), name="medical-workflow-symptom-create"),  # 工作流：创建症状
    path("workflows/visits/create/", VisitWorkflowCreateView.as_view(), name="medical-workflow-visit-create"),  # 工作流：创建就诊
    path("workflows/surgeries/create/", SurgeryWorkflowCreateView.as_view(), name="medical-workflow-surgery-create"),  # 工作流：创建手术
    path("workflows/follow-ups/create/", FollowUpWorkflowCreateView.as_view(), name="medical-workflow-follow-up-create"),  # 工作流：创建随访
    path("workflows/attachments/batch-bind/", MedicalAttachmentBatchBindView.as_view(), name="medical-workflow-attachment-batch-bind"),  # 工作流：批量绑定附件到业务实体
    path("combined-create/", CombinedMedicalCreateAPIView.as_view(), name="medical-combined-create"),  # 组合创建：病例及关联子资源一次性入库
]
