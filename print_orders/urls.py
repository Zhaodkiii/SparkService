from django.urls import path
from . import views as v
urlpatterns=[path('products/',v.Products.as_view()),path('quotes/',v.Quote.as_view()),
 path('orders/',v.Orders.as_view()),path('orders/<uuid:pk>/',v.Detail.as_view()),
 path('orders/<uuid:pk>/upload/',v.Upload.as_view()),path('orders/<uuid:pk>/complete-upload/',v.CompleteUpload.as_view()),
 path('orders/<uuid:pk>/payments/',v.Payment.as_view()),path('orders/<uuid:pk>/refresh-payment/',v.RefreshPayment.as_view()),
 path('orders/<uuid:pk>/actions/',v.UserAction.as_view()),path('wechat-notify/',v.Notification.as_view())]
