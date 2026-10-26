from django.urls import path
from . import views as v
from . import payment_views as pay
urlpatterns=[path("payments/access/",pay.Access.as_view()),path("payments/overview/",pay.Overview.as_view()),path("payments/export/",pay.LedgerExport.as_view()),path("payments/probes/",pay.Probes.as_view()),path("payments/channels/",pay.Channels.as_view()),path("payments/transactions/",pay.Transactions.as_view()),path("payments/refunds/",pay.Refunds.as_view()),path("payments/audit/",pay.Audit.as_view()),path('products/',v.AdminProducts.as_view()),path('orders/',v.AdminOrders.as_view()),
 path('orders/<uuid:pk>/',v.AdminDetail.as_view()),path('orders/<uuid:pk>/downloads/',v.Downloads.as_view())]
