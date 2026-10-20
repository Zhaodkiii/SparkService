from django.core.checks import Error,register
from django.conf import settings

@register()
def private_namespace_is_separate(app_configs,**kwargs):
    public=getattr(settings,'DIARY_PRESETS_OSS_PREFIX','traveldiary/presets/').strip('/')+'/'
    private=getattr(settings,'CUSTOMIZATIONS_OSS_PREFIX','traveldiary/customizations/').strip('/')+'/'
    if public.startswith(private) or private.startswith(public):
        return [Error('私人定制和公共模板的 OSS 前缀不可包含或重叠',id='diary_customizations.E001')]
    return []
