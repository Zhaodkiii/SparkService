from django.urls import path
from . import views as v
urlpatterns=[path('products/',v.AdminProducts.as_view()),path('orders/',v.AdminOrders.as_view()),
 path('orders/<uuid:pk>/',v.AdminDetail.as_view()),path('orders/<uuid:pk>/downloads/',v.Downloads.as_view())]
