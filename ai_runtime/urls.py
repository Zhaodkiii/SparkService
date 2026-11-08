from django.urls import path
from . import views as v
urlpatterns = [
    path('manifest/', v.Manifest.as_view()),
    path('tasks/<uuid:task_id>/configuration/', v.Configuration.as_view()),
    path('tasks/<uuid:task_id>/events/', v.Events.as_view()),
]
admin_urlpatterns = [
    path('drafts/current/', v.Draft.as_view()), path('validation/', v.Validation.as_view()),
    path('tests/', v.Tests.as_view()), path('tests/<uuid:pk>/', v.Tests.as_view()),
    path('releases/', v.Releases.as_view()), path('releases/<uuid:pk>/', v.Releases.as_view()),
    path('releases/<uuid:pk>/rollback/', v.Releases.as_view()), path('controls/', v.Controls.as_view()),
    path('credential-slots/<uuid:pk>/versions/', v.Credentials.as_view()),
    path('credential-slots/<uuid:pk>/activate/', v.Activate.as_view()),
]
for kind in v.CATALOG:
    admin_urlpatterns += [path(kind+'/', v.Catalog.as_view(), {'kind': kind}),
                          path(kind+'/<uuid:pk>/', v.Catalog.as_view(), {'kind': kind})]
for kind in ('audits', 'deliveries', 'events'):
    admin_urlpatterns.append(path(kind+'/', v.Records.as_view(), {'kind': kind}))
