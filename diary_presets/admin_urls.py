from rest_framework.routers import DefaultRouter
from .views import SeriesAdmin, TemplateAdmin, UploadAdmin
router = DefaultRouter()
router.register('series', SeriesAdmin)
router.register('templates', TemplateAdmin)
router.register('uploads', UploadAdmin)
urlpatterns = router.urls
