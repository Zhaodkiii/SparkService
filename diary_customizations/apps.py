from django.apps import AppConfig

class DiaryCustomizationsConfig(AppConfig):
    default_auto_field='django.db.models.BigAutoField'
    name='diary_customizations'
    verbose_name='专属手帐定制'
    def ready(self):
        from . import checks  # noqa: F401
