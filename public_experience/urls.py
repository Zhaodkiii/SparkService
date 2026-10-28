from django.urls import path
from . import views
urlpatterns = [path('bootstrap/', views.bootstrap), path('templates/', views.templates)]
