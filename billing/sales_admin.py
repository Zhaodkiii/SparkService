from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from common.permissions import SuperAdminOnlyPermission
from .views import AuthView
from .models import SalesControl,BillingAudit
from .flags import sales_enabled,RUNTIME_FLAGS


def state(control=None):
    control=control or SalesControl.objects.filter(pk=1).first()
    return dict(environment=settings.MATERIAL_SYNC_ENVIRONMENT_ID or '未标记环境',revision=control.revision if control else 0,
        **{field:getattr(control,field) if control else bool(getattr(settings,key,False)) for key,field in RUNTIME_FLAGS.items()},
        updated_at=control.updated_at if control else None,updated_by=control.updated_by.get_username() if control and control.updated_by else None)

class Input(serializers.Serializer):
    expected_revision=serializers.IntegerField(min_value=0)
    diamond_redemption_enabled=serializers.BooleanField()
    membership_sales_enabled=serializers.BooleanField()
    reason=serializers.CharField(max_length=500,allow_blank=False)

class SalesSettings(AuthView):
    permission_classes=[SuperAdminOnlyPermission]
    def get(self,request):return Response(state())
    @transaction.atomic
    def patch(self,request):
        form=Input(data=request.data);form.is_valid(raise_exception=True);data=form.validated_data
        control,_=SalesControl.objects.get_or_create(pk=1,defaults={field:bool(getattr(settings,key,False)) for key,field in RUNTIME_FLAGS.items()})
        control=SalesControl.objects.select_for_update().get(pk=1)
        if control.revision!=data['expected_revision']:
            return Response({'code':'SALES_CHANGED','message':'销售开关已被其他管理员修改，请刷新后重试'},status=409)
        before=state(control)
        for field in RUNTIME_FLAGS.values():setattr(control,field,data[field])
        control.revision+=1;control.updated_by=request.user;control.save()
        BillingAudit.objects.create(actor=request.user,action='change_sales_control',target='sales-control',detail={'environment':before['environment'],'before':{f:before[f] for f in RUNTIME_FLAGS.values()},'after':{f:data[f] for f in RUNTIME_FLAGS.values()},'reason':data['reason'],'revision':control.revision})
        return Response(state(control))
