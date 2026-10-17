from django.urls import path
from .views import Catalog, Browse, Detail, PlanURLs

urlpatterns = [
    path('catalog/', Catalog.as_view()),
    path('templates/<uuid:pk>/<int:number>/browse/', Browse.as_view()),
    path('templates/<uuid:pk>/<int:number>/', Detail.as_view()),
    path('plans/<uuid:pk>/urls/', PlanURLs.as_view()),
]
