from rest_framework.routers import DefaultRouter
from .views import SeriesAdmin, TemplateAdmin, UploadAdmin
from .search_views import TaxonAdmin, ReadingUnitAdmin
router = DefaultRouter()
router.register('tags', TaxonAdmin, basename='preset-taxon')
router.register('reading-units', ReadingUnitAdmin, basename='preset-reading-unit')
router.register('series', SeriesAdmin)
router.register('templates', TemplateAdmin)
router.register('uploads', UploadAdmin)
urlpatterns = router.urls

from django.urls import path
from . import sync_api as sync
urlpatterns += [
    path('sync/options/', sync.SyncOptions.as_view()),
    path('templates/<uuid:pk>/production-sync/preflight/', sync.SourcePreflight.as_view()),
    path('templates/<uuid:pk>/sync-history/', sync.SourceHistory.as_view()),
    path('sync-tasks/<uuid:pk>/', sync.SourceTask.as_view()),
    path('sync-tasks/<uuid:pk>/confirm/', sync.SourceConfirm.as_view()),
    path('sync-tasks/<uuid:pk>/retry/', sync.SourceRetry.as_view()),
]
