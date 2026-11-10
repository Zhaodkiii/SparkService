from django.urls import path
from . import views as v
from . import payment_views as pay
from .campaigns import Placement, Enroll, Withdraw, AnnualOffer, Wallet
urlpatterns=[path("coupons/mine/",Wallet.as_view()),path("campaign/annual/",AnnualOffer.as_view()),path("campaign/", Placement.as_view()),path("campaign/<int:pk>/join/",Enroll.as_view()),path("campaign/<int:pk>/withdraw/",Withdraw.as_view()),path("payment-probes/<uuid:pk>/launch/",pay.ProbeLaunch.as_view()),path('products/',v.Products.as_view()),path('quotes/',v.Quote.as_view()),
 path('orders/',v.Orders.as_view()),path('orders/<uuid:pk>/',v.Detail.as_view()),
 path('orders/<uuid:pk>/upload/',v.Upload.as_view()),path('orders/<uuid:pk>/complete-upload/',v.CompleteUpload.as_view()),
 path('orders/<uuid:pk>/payments/',pay.Pay.as_view()),path('orders/<uuid:pk>/refresh-payment/',v.RefreshPayment.as_view()),
 path('orders/<uuid:pk>/actions/',v.UserAction.as_view()),path('payment-methods/',pay.Methods.as_view()),path('wechat-notify/',pay.Notify.as_view(),{'channel':'wechat'}),path('alipay-notify/',pay.Notify.as_view(),{'channel':'alipay'})]
