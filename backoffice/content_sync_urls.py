from django.urls import path
from . import content_sync as v
urlpatterns=[path('catalog/',v.Catalog.as_view()),path('batches/',v.Batches.as_view()),
    path('batches/<uuid:pk>/',v.Detail.as_view()),path('batches/<uuid:pk>/confirm/',v.Confirm.as_view()),path('batches/<uuid:pk>/retry/',v.Retry.as_view())]
