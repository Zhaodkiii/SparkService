from django.urls import path

from task_system.views import (
    AITaskCandidateAnalyzeAPI,
    TaskCancelAPI,
    TaskCompleteAPI,
    TaskDetailAPI,
    TaskExecutionListAPI,
    TaskListCreateAPI,
    TaskNotificationListAPI,
    TaskQueryByMemberAPI,
    TaskSyncAPI,
)

urlpatterns = [
    path("", TaskListCreateAPI.as_view(), name="task-list-create"),
    path("sync/", TaskSyncAPI.as_view(), name="task-sync"),
    path("ai/query-by-member/", TaskQueryByMemberAPI.as_view(), name="task-ai-query-by-member"),
    path("ai/candidate-analyze/", AITaskCandidateAnalyzeAPI.as_view(), name="task-ai-candidate-analyze"),
    path("<int:task_id>/", TaskDetailAPI.as_view(), name="task-detail"),
    path("<int:task_id>/complete/", TaskCompleteAPI.as_view(), name="task-complete"),
    path("<int:task_id>/cancel/", TaskCancelAPI.as_view(), name="task-cancel"),
    path("<int:task_id>/executions/", TaskExecutionListAPI.as_view(), name="task-executions"),
    path("<int:task_id>/notifications/", TaskNotificationListAPI.as_view(), name="task-notifications"),
]
