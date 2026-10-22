from rest_framework.throttling import SimpleRateThrottle

class HelpReadThrottle(SimpleRateThrottle):
    rate='120/min'
    scope='support_help'
    def get_cache_key(self,request,view):
        identity=str(request.user.pk) if request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {'scope':self.scope,'ident':identity}

class SupportRequestThrottle(HelpReadThrottle):
    rate='300/min'
    scope='support_private'
