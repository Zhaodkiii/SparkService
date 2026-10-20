from django.urls import path
from diary_presets.views import PresetAdmin
from . import views as v
class Requests(v.Requests): permission_classes=[PresetAdmin];admin=True
class Detail(v.RequestDetail): permission_classes=[PresetAdmin];admin=True
class Action(v.Action): permission_classes=[PresetAdmin];admin=True
class Upload(v.Upload): permission_classes=[PresetAdmin];admin=True
class AssetURLs(v.AssetURLs): permission_classes=[PresetAdmin];admin=True
urlpatterns=[path('operators/',v.Operators.as_view()),path('requests/',Requests.as_view()),path('requests/<uuid:pk>/',Detail.as_view()),
 path('requests/<uuid:pk>/operations/',v.OperationStatus.as_view()),path('requests/<uuid:pk>/asset-urls/',AssetURLs.as_view()),
 path('requests/<uuid:pk>/delivery-uploads/',v.DeliveryUploads.as_view()),
 path('requests/<uuid:pk>/source-export/',v.Export.as_view()),path('requests/<uuid:pk>/<str:action>/',Action.as_view()),
 path('uploads/<uuid:pk>/',Upload.as_view()),path('uploads/<uuid:pk>/<str:action>/',Upload.as_view())]
