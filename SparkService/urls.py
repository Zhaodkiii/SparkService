"""
URL configuration for SparkService project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.http import JsonResponse
from django.urls import include, path
from django.conf.urls.static import static
from accounts.auth.views import TokenObtainUnifiedView, TokenRefreshView


def health_check(_request):
    return JsonResponse({"status": "ok", "service": "SparkService 哈哈哈请求成功更新成功啦"})


from diary_presets.views import Processor
from diary_customizations.processor import Processor as CustomizationProcessor
from diary_presets.resource_queue import Processor as ResourceProcessor


urlpatterns = [
    path("api/v1/support/", include("support_center.urls")),
    path("api/admin/v1/support/", include("support_center.admin_urls")),
    path("api/v1/diary-customizations/", include("diary_customizations.urls")),
    path("api/admin/v1/diary-customizations/", include("diary_customizations.admin_urls")),
    path("api/internal/diary-customizations/processor/", CustomizationProcessor.as_view()),
    path("api/v1/print/", include("print_orders.urls")),
    path("api/admin/v1/print/", include("print_orders.admin_urls")),
    path("api/v1/materials/", include("material_library.urls")),
    path("api/v1/diary-presets/", include("diary_presets.urls")),
    path("api/admin/v1/diary-presets/", include("diary_presets.admin_urls")),
    path("api/internal/diary-presets/processor/", ResourceProcessor.as_view()),
    path('health/', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('api/v1/auth/token/', TokenObtainUnifiedView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/', include('accounts.urls')),
    path('api/v1/ai/', include('ai_config.urls')),
    path('api/v1/files/', include('file_manager.urls')),
    path('api/v1/oss/', include('file_manager.oss_urls')),
    path('api/admin/v1/', include('backoffice.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
