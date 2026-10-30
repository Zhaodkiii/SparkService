from django.urls import path
from . import views as v
urlpatterns=[path('bootstrap/',v.Bootstrap.as_view()),path('wallet/',v.Wallet.as_view()),path('wallet/sync/',v.Wallet.as_view()),path('wallet/entries/',v.Entries.as_view()),path('recharge-products/',v.Products.as_view()),path('redemption-quotes/',v.Quotes.as_view()),path('redemptions/',v.Redemptions.as_view()),path('redemptions/<uuid:pk>/',v.Redemptions.as_view()),path('content-ownerships/',v.Ownerships.as_view()),path('revenuecat/webhook/',v.Webhook.as_view())]
from .manage import ManageOffers,ManagePolicy,ManageCatalog
urlpatterns += [path('manage/content-offers/',ManageOffers.as_view()),path('manage/content-offers/<uuid:pk>/<str:action>/',ManagePolicy.as_view())]
urlpatterns += [path('content-access/<str:kind>/<uuid:pk>/',v.ContentAccess.as_view())]
from .manage import ManagePackages,ManageCustomizationQuote
urlpatterns += [path('manage/customization-packages/',ManagePackages.as_view()),path('manage/customizations/<uuid:pk>/quote/',ManageCustomizationQuote.as_view()),path('customizations/<uuid:pk>/',v.CustomizationPayment.as_view())]
from .manage import ManageOperations,ManageCompensation
urlpatterns += [path('manage/operations/',ManageOperations.as_view()),path('manage/operations/<uuid:pk>/compensate/',ManageCompensation.as_view())]

urlpatterns += [path('sandbox-webhook/',v.SandboxWebhook.as_view())]
from .transactions import Transactions,PaymentDetail,UserAssets
urlpatterns += [path('manage/transactions/',Transactions.as_view()),path('manage/transactions/<uuid:pk>/',PaymentDetail.as_view()),path('manage/assets/<uuid:pk>/',UserAssets.as_view())]

urlpatterns += [path('membership/', v.Membership.as_view())]

urlpatterns += [path('manage/content-catalog/', ManageCatalog.as_view())]

from .operations_admin import ManageOperationDetail
urlpatterns += [path('manage/operations/<uuid:pk>/', ManageOperationDetail.as_view())]

from .sales_admin import SalesSettings
urlpatterns += [path('manage/sales-settings/',SalesSettings.as_view())]

from .batch_pricing import BatchPricing
urlpatterns += [path('manage/batch-pricing/<str:action>/', BatchPricing.as_view())]
