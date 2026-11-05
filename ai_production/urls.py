from django.urls import path, register_converter
from .converters import ProductionUUIDConverter

register_converter(ProductionUUIDConverter, "production_uuid")
from .views import QuotaView, TaskListView, TaskDetailView, TaskActionView, TaskCompleteView

urlpatterns = [
    path("tasks/<production_uuid:task_id>/complete/", TaskCompleteView.as_view()),
    path("quota/", QuotaView.as_view()),
    path("tasks/", TaskListView.as_view()),
    path("tasks/<production_uuid:task_id>/", TaskDetailView.as_view()),
    path("tasks/<production_uuid:task_id>/<str:action>/", TaskActionView.as_view()),
]
