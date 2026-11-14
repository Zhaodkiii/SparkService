from django.urls import path, register_converter
from .converters import ProductionUUIDConverter

register_converter(ProductionUUIDConverter, "production_uuid")
from .views import QuotaView, TaskListView, TaskDetailView, TaskActionView, TaskCompleteView, CallListView, CallDetailView, CallUsageView

urlpatterns = [
    path("tasks/<production_uuid:task_id>/calls/", CallListView.as_view()),
    path("tasks/<production_uuid:task_id>/calls/<production_uuid:call_id>/", CallDetailView.as_view()),
    path("tasks/<production_uuid:task_id>/calls/<production_uuid:call_id>/usage/", CallUsageView.as_view()),
    path("tasks/<production_uuid:task_id>/complete/", TaskCompleteView.as_view()),
    path("quota/", QuotaView.as_view()),
    path("tasks/", TaskListView.as_view()),
    path("tasks/<production_uuid:task_id>/", TaskDetailView.as_view()),
    path("tasks/<production_uuid:task_id>/<str:action>/", TaskActionView.as_view()),
]
