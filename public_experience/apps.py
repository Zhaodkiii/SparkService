from django.apps import AppConfig
class PublicExperienceConfig(AppConfig):
    name='public_experience'
    def ready(self):
        from . import signals
