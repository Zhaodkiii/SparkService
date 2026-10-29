from django.urls import path
from . import views
urlpatterns = [path('bootstrap/', views.bootstrap), path('templates/', views.templates)]
from . import books
urlpatterns += [
    path('books/', books.books),
    path('books/<uuid:pk>/<int:number>/browse/', books.browse),
    path('books/<uuid:pk>/<int:number>/pages/<str:page_id>/preview/', books.page_preview),
    path('books/<uuid:pk>/<int:number>/pages/<str:page_id>/projection/', books.projection),
]
urlpatterns += [path('books/<uuid:pk>/<int:number>/pages/<str:page_id>/slots/', books.slots)]
