from django.urls import path
from . import sync_api as v
urlpatterns=[
 path('capabilities/',v.Capabilities.as_view()),
 path('preflights/',v.ReceivePreflight.as_view()),
 path('preflights/<uuid:pk>/',v.ReceiveTask.as_view()),
 path('imports/',v.ReceiveImport.as_view()),
 path('imports/by-key/<str:key>/',v.ReceiveByKey.as_view()),
 path('imports/<uuid:pk>/',v.ReceiveTask.as_view()),
]
