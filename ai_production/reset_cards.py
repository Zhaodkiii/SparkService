import uuid
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from common.response import success_response
from .models import ProductionResetCard, ProductionWindow, ProductionCall
from . import services
from .entitlements import prepare_identity, entitlement


def card_data(c):
    return dict(id=str(c.pk),expires_at=c.expires_at,status='used' if c.used_reset_id else 'revoked' if c.revoked_at else 'expired' if c.expires_at<=timezone.now() else 'available')


@transaction.atomic
def use_card(user,card_id,key,expected_plan,identity):
    services.lock_account(user)
    c=get_object_or_404(ProductionResetCard.objects.select_for_update(),pk=card_id,owner=user)
    if c.used_reset_id:
        if c.used_reset.request_key==key: return c
        raise ValidationError('重置卡已使用')
    if c.revoked_at or c.expires_at<=timezone.now(): raise ValidationError('重置卡已失效')
    plan,_=entitlement(identity,lock=True)
    if not plan or plan!=expected_plan: raise ValidationError('会员状态已变化，请重新确认')
    services.expire_calls(user)
    if ProductionCall.objects.filter(task__account=user,accounting_state='pending').exists(): raise ValidationError('调用正在记账，请稍后重试')
    kinds=['weekly','short'] if plan=='pro' else ['weekly']
    now=timezone.now()
    if not ProductionWindow.objects.filter(account=user,kind__in=kinds,starts_at__lte=now,ends_at__gt=now,used_points__gt=0).exists():
        raise ValidationError('额度已经恢复，无需消耗重置卡')
    c.used_reset=services.reset_quota(user,user,key,'both' if plan=='pro' else 'weekly',f'用户使用重置卡 {c.pk}',expected_plan=plan,identity=identity)
    c.save(update_fields=['used_reset'])
    return c


class ResetCardView(APIView):
    permission_classes=[IsAuthenticated]
    def post(self,request,card_id,action):
        identity=prepare_identity(request)
        if action=='preview':
            c=get_object_or_404(ProductionResetCard,pk=card_id,owner=request.user)
            q=services.quota(request.user,identity=identity)
            return success_response(dict(card=card_data(c),quota=q,plan=q['plan']))
        if action!='use': raise ValidationError('未知操作')
        try: key=uuid.UUID(request.headers.get('Idempotency-Key',''))
        except ValueError: raise ValidationError('缺少幂等请求编号')
        c=use_card(request.user,card_id,key,request.data.get('expected_plan'),identity)
        return success_response(dict(card=card_data(c),quota=services.quota(request.user,identity=identity)))
