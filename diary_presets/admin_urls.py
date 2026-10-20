from rest_framework.routers import DefaultRouter
from .views import SeriesAdmin, TemplateAdmin, UploadAdmin
from .search_views import TaxonAdmin, ReadingUnitAdmin
router = DefaultRouter()
router.register('tags', TaxonAdmin, basename='preset-taxon')
router.register('reading-units', ReadingUnitAdmin, basename='preset-reading-unit')
router.register('series', SeriesAdmin)
router.register('templates', TemplateAdmin)
router.register('uploads', UploadAdmin)
urlpatterns = router.urls
