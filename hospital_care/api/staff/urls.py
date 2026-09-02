from django.urls import path

from hospital_care.api.staff.views import (
    DoctorConversationAttentionView,
    DoctorConversationDetailView,
    DoctorConversationEndView,
    DoctorConversationJoinView,
    DoctorConversationListView,
    DoctorConversationMessagesView,
    DoctorWorkspaceView,
    StaffAgentSubmitView,
    StaffAgentView,
    StaffMeView,
    StaffWorkLogView,
)

urlpatterns = [
    path("me/", StaffMeView.as_view(), name="hospital-care-staff-me"),
    path("me/agent/", StaffAgentView.as_view(), name="hospital-care-staff-agent"),
    path("me/agent/submit/", StaffAgentSubmitView.as_view(), name="hospital-care-staff-agent-submit"),
    path("me/work-logs/", StaffWorkLogView.as_view(), name="hospital-care-staff-work-logs"),
    path("me/workspace/", DoctorWorkspaceView.as_view(), name="hospital-care-staff-workspace"),
    path("doctor/conversations/", DoctorConversationListView.as_view(), name="hospital-care-staff-conversations"),
    path("doctor/conversations/<uuid:thread_id>/", DoctorConversationDetailView.as_view(), name="hospital-care-staff-conversation-detail"),
    path("doctor/conversations/<uuid:thread_id>/messages/", DoctorConversationMessagesView.as_view(), name="hospital-care-staff-messages"),
    path("doctor/conversations/<uuid:thread_id>/join/", DoctorConversationJoinView.as_view(), name="hospital-care-staff-join"),
    path("doctor/conversations/<uuid:thread_id>/attention/", DoctorConversationAttentionView.as_view(), name="hospital-care-staff-attention"),
    path("doctor/conversations/<uuid:thread_id>/end/", DoctorConversationEndView.as_view(), name="hospital-care-staff-end"),
]
