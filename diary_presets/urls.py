from django.urls import path
from .views import Catalog, Browse, Detail, PlanURLs
from .search_views import Search, Taxonomy

from .import_statistics import ImportEvents

urlpatterns = [
    path('import-events/', ImportEvents.as_view()),
    path('search/', Search.as_view()),
    path('taxonomy/', Taxonomy.as_view()),
    path('catalog/', Catalog.as_view()),
    path('templates/<uuid:pk>/<int:number>/browse/', Browse.as_view()),
    path('templates/<uuid:pk>/<int:number>/', Detail.as_view()),
    path('plans/<uuid:pk>/urls/', PlanURLs.as_view()),
]
