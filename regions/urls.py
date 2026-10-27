from django.urls import path
from . import views
urlpatterns=[path('manifest/',views.manifest),path('datasets/<slug:version>.json',views.dataset)]
