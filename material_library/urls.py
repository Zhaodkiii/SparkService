from django.urls import path
from . import views
urlpatterns = [
 path('available/',views.Available.as_view()),
 path('items/',views.Items.as_view()),
 path('categories/',views.Categories.as_view()),
 path('libraries/',views.Libraries.as_view()),
 path('libraries/<uuid:pk>/items/',views.Items.as_view()),
 path('<str:target>/<uuid:pk>/favorite/',views.Favorite.as_view()),
 path('revisions/<int:pk>/download/',views.Download.as_view()),
 path('manage/<uuid:template>/',views.Manage.as_view()),
]

from . import catalog_v2 as catalog, management_api as admin
urlpatterns += [
 path('manage/options/', admin.Options.as_view()),
 path('manage/templates/', admin.Templates.as_view()),
 path('libraries/<uuid:pk>/', catalog.LibraryDetail.as_view()),
 path('items/<uuid:pk>/', catalog.ItemDetail.as_view()),
 path('tags/', catalog.Tags.as_view()),
 path('previews/resolve/', catalog.Previews.as_view()),
 path('manage/libraries/', admin.Libraries.as_view()),
 path('manage/libraries/<uuid:pk>/draft/', admin.Draft.as_view()),
 path('manage/libraries/<uuid:pk>/validate/', admin.Validate.as_view()),
 path('manage/libraries/<uuid:pk>/publish/', admin.Publish.as_view()),
 path('manage/libraries/<uuid:pk>/availability/', admin.Availability.as_view()),
 path('manage/libraries/<uuid:pk>/placement/', admin.Placement.as_view()),
 path('manage/libraries/<uuid:pk>/versions/', admin.Versions.as_view()),
 path('manage/libraries/<uuid:pk>/restore-draft/', admin.Restore.as_view()),
 path('manage/materials/', admin.Materials.as_view()),
 path('manage/materials/<uuid:pk>/revisions/', admin.Revisions.as_view()),
 path('manage/materials/<uuid:pk>/usage/', admin.MaterialUsage.as_view()),
 path('manage/materials/<uuid:pk>/availability/', admin.MaterialAvailability.as_view()),
 path('manage/uploads/', admin.Uploads.as_view()),
 path('manage/uploads/<uuid:pk>/', admin.UploadDetail.as_view()),
 path('manage/uploads/<uuid:pk>/complete/', admin.UploadComplete.as_view()),
 path('manage/jobs/<uuid:pk>/', admin.UploadDetail.as_view()),
 path('manage/categories/', admin.Dictionary.as_view(), {'target':'categories'}),
 path('manage/tags/', admin.Dictionary.as_view(), {'target':'tags'}),
 path('manage/audit-logs/', admin.Audit.as_view()),
]

from . import sync_api as sync
urlpatterns += [
 path('manage/sync/options/',sync.SyncOptions.as_view()),
 path('manage/libraries/<uuid:pk>/production-sync/preflight/',sync.SourcePreflight.as_view()),
 path('manage/libraries/<uuid:pk>/sync-history/',sync.SourceHistory.as_view()),
 path('manage/sync-tasks/<uuid:pk>/',sync.SourceTask.as_view()),
 path('manage/sync-tasks/<uuid:pk>/confirm/',sync.SourceConfirm.as_view()),
 path('manage/sync-tasks/<uuid:pk>/retry/',sync.SourceRetry.as_view()),
]
