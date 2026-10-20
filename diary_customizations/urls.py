from django.urls import path
from . import views as v
urlpatterns=[path('config/',v.Config.as_view()),path('requests/',v.Requests.as_view()),
 path('notification-summary/',v.Summary.as_view()),path('preferences/',v.Preference.as_view()),
 path('requests/<uuid:pk>/',v.RequestDetail.as_view()),path('requests/<uuid:pk>/read/',v.Read.as_view()),
 path('requests/<uuid:pk>/asset-urls/',v.AssetURLs.as_view()),
 path('requests/<uuid:pk>/uploads/',v.Assets.as_view()),path('requests/<uuid:pk>/assets/<uuid:asset>/',v.AssetDetail.as_view()),
 path('requests/<uuid:pk>/<str:action>/',v.Action.as_view()),path('uploads/<uuid:pk>/',v.Upload.as_view()),
 path('uploads/<uuid:pk>/<str:action>/',v.Upload.as_view())]
