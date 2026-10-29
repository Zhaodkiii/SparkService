from django.urls import path
from . import api
from .processor import Processor
urlpatterns=[
 path('families/',api.Catalog.as_view()),path('families/<uuid:pk>/',api.Catalog.as_view()),
 path('mine/',api.Personal.as_view()),path('families/<uuid:pk>/<str:action>/',api.Personal.as_view()),
 path('download-plans/',api.Download.as_view()),path('processor/',Processor.as_view()),
 path('manage/options/',api.Options.as_view()),path('manage/families/',api.Families.as_view()),
 path('manage/families/<uuid:pk>/<str:action>/',api.FamilyAdmin.as_view()),
 path('manage/uploads/',api.Uploads.as_view()),path('manage/uploads/<uuid:pk>/complete/',api.UploadComplete.as_view()),
]

from . import sync_api as sync
urlpatterns += [
 path('manage/sync/options/',sync.SyncOptions.as_view()),
 path('manage/families/<uuid:pk>/production-sync/preflight/',sync.SourcePreflight.as_view()),
 path('manage/families/<uuid:pk>/sync-history/',sync.SourceHistory.as_view()),
 path('manage/sync-tasks/<uuid:pk>/',sync.SourceTask.as_view()),
 path('manage/sync-tasks/<uuid:pk>/confirm/',sync.SourceConfirm.as_view()),
 path('manage/sync-tasks/<uuid:pk>/retry/',sync.SourceRetry.as_view()),
]
