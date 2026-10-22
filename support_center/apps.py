from django.apps import AppConfig
class SupportCenterConfig(AppConfig):
    name='support_center'
    def ready(self):
        from . import signals  # noqa: F401
