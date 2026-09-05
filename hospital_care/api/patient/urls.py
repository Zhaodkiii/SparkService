from django.urls import path

from hospital_care.api.patient.views import (
    AgentDetailView,
    AgentRuntimeConfigView,
    AppointmentRedirectView,
    ConsultationListCreateView,
    ConversationCreateView,
    HospitalAgentListView,
    HospitalDepartmentListView,
    HospitalHomeView,
    HospitalListView,
    PatientConversationContextView,
    PatientKnowledgeSyncPullView,
    RegistrationEntryView,
)

urlpatterns = [
    path("hospitals/", HospitalListView.as_view(), name="hospital-care-patient-hospitals"),
    path("hospitals/<uuid:hospital_id>/home/", HospitalHomeView.as_view(), name="hospital-care-patient-home"),
    path("hospitals/<uuid:hospital_id>/departments/", HospitalDepartmentListView.as_view(), name="hospital-care-patient-departments"),
    path("hospitals/<uuid:hospital_id>/agents/", HospitalAgentListView.as_view(), name="hospital-care-patient-agents"),
    path("hospitals/<uuid:hospital_id>/registration/entry/", RegistrationEntryView.as_view(), name="hospital-care-patient-registration"),
    path("agents/<uuid:agent_id>/", AgentDetailView.as_view(), name="hospital-care-patient-agent-detail"),
    path("agents/<uuid:agent_id>/runtime-config/", AgentRuntimeConfigView.as_view(), name="hospital-care-patient-agent-runtime-config"),
    path("conversations/", ConversationCreateView.as_view(), name="hospital-care-patient-conversations"),
    path("consultations/", ConsultationListCreateView.as_view(), name="hospital-care-patient-consultations"),
    path("conversations/<uuid:thread_id>/context/", PatientConversationContextView.as_view(), name="hospital-care-patient-conversation-context"),
    path("knowledge-bases/<uuid:knowledge_base_id>/sync/pull/", PatientKnowledgeSyncPullView.as_view(), name="hospital-care-patient-knowledge-pull"),
    path("appointments/redirect/", AppointmentRedirectView.as_view(), name="hospital-care-patient-appointment-redirect"),
]
