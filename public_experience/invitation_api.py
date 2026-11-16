from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.db.models import Count
from rest_framework import serializers
from rest_framework.permissions import AllowAny,IsAuthenticated,BasePermission
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError,PermissionDenied
from common.response import success_response
from .models import *
from . import invitations as svc
from . import invitation_otp

class PublicLimit(AnonRateThrottle):
    rate='20/hour'

class CampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model=InvitationCampaign
        fields='__all__'
        read_only_fields=['version','created_at','print_snapshot']


def campaign_data(c):
    return dict(id=c.pk,title=c.title,rules=c.rules,ends_at=c.ends_at,download_url=c.download_url,
        cards_per_invite=c.cards_per_invite,card_days=c.card_days,card_invite_limit=c.card_invite_limit,
        automatic=c.automatic,attribution_days=c.attribution_days,available=svc.available(c),
        remaining_slots=max(0,c.participant_limit-InvitationLink.objects.filter(campaign=c).count()))

class Landing(APIView):
    permission_classes=[AllowAny]
    authentication_classes=[]
    throttle_classes=[PublicLimit]
    def get(self,request,token):
        link=get_object_or_404(InvitationLink.objects.select_related('campaign'),pk=token)
        return success_response(campaign_data(link.campaign))
    def post(self,request,token):
        link=get_object_or_404(InvitationLink.objects.select_related('campaign','owner'),pk=token)
        class Input(serializers.Serializer):
            contact_kind=serializers.ChoiceField(choices=['phone','email'])
            contact=serializers.CharField(max_length=254)
            challenge_id=serializers.UUIDField()
            code=serializers.RegexField(r'^[0-9]{6}$')
            consent=serializers.BooleanField()
        data=Input(data=request.data);data.is_valid(raise_exception=True)
        values=data.validated_data
        if not values['consent']: raise ValidationError('请先阅读并同意活动规则与隐私政策')
        r=invitation_otp.verify_and_register(link,values['contact_kind'],values['contact'],values['challenge_id'],values['code'])
        return success_response(dict(registration_id=str(r.pk),status='awaiting_app',expires_at=r.expires_at,download_url=link.campaign.download_url))

class InvitationCode(Landing):
    http_method_names = ['post', 'options']

    def post(self, request, token):
        link = get_object_or_404(InvitationLink.objects.select_related('campaign', 'owner'), pk=token)
        class Input(serializers.Serializer):
            contact_kind = serializers.ChoiceField(choices=['phone', 'email'])
            contact = serializers.CharField(max_length=254)
            consent = serializers.BooleanField()
        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if not values['consent']:
            raise ValidationError('请先阅读并同意活动规则与隐私政策')
        return success_response(invitation_otp.request_code(link, values['contact_kind'], values['contact']))

class MyInvitation(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        now=timezone.now()
        c=InvitationCampaign.objects.filter(active=True,starts_at__lte=now,ends_at__gt=now).order_by('-pk').first()
        if not c: return success_response(dict(campaign=None,link=None,invite_token=None,invite_path=None,count=0,records=[]))
        link=InvitationLink.objects.filter(campaign=c,owner=request.user).first()
        records=[]; count=0
        if link:
            count=InvitationConversion.objects.filter(registration__link=link).count()
            records=[dict(id=str(r.pk),created_at=r.created_at,expires_at=r.expires_at,status='confirmed' if hasattr(r,'invitationconversion') else 'expired' if r.expires_at<=now else 'awaiting_app') for r in InvitationRegistration.objects.filter(link=link).order_by('-created_at')[:100]]
        path = f'/invite/{link.pk}' if link else None
        # Older clients still consume link; derive it from this request, never a fixed environment setting.
        campaign=campaign_data(c)
        campaign['joined']=link is not None
        return success_response(dict(campaign=campaign,
            invite_token=str(link.pk) if link else None, invite_path=path,
            link=request.build_absolute_uri(path) if path else None, count=count,records=records))
    def post(self,request):
        c=get_object_or_404(InvitationCampaign,pk=request.data.get('campaign_id'))
        svc.join(request.user,c)
        return self.get(request)

class Rewards(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        from ai_production.models import ProductionResetCard
        from ai_production.reset_cards import card_data
        from print_orders.models import PrintCoupon
        return success_response(dict(
            cards=[card_data(c) for c in ProductionResetCard.objects.filter(owner=request.user).order_by('-issued_at')[:100]],
            coupons=[dict(id=str(c.pk),name=c.name,expires_at=c.expires_at,status='used' if c.order_id else 'expired' if c.expires_at<=timezone.now() else 'available') for c in PrintCoupon.objects.filter(owner=request.user).order_by('-issued_at')[:100]],
            grants=list(InvitationReward.objects.filter(link__owner=request.user).order_by('-pk').values('id','kind','threshold','quantity','issued_at')[:100])))

def permitted(user,code):
    from backoffice.rbac import has_permission_code
    return user.is_authenticated and user.is_active and (user.has_perm(code) or has_permission_code(user.pk,code))

class AdminPermission(BasePermission):
    def has_permission(self,request,view):
        if request.method != 'GET' and request.data.get('action') == 'revoke_card':
            return permitted(request.user,'ai_production.change_productionresetcard')
        perm='view_invitationcampaign' if request.method=='GET' else 'add_invitationreward' if request.data.get('action')=='issue' else 'change_invitationcampaign'
        return permitted(request.user,'public_experience.'+perm)

class AdminInvitations(APIView):
    permission_classes=[AdminPermission]
    def get(self,request):
        from print_orders.models import PrintCampaign
        from ai_production.models import ProductionResetCard
        from ai_production.reset_cards import card_data
        return success_response(dict(cards=[dict(card_data(c),owner_id=c.owner_id,grant_key=c.grant_key) for c in ProductionResetCard.objects.order_by('-issued_at')[:200]],campaigns=CampaignSerializer(InvitationCampaign.objects.order_by('-pk')[:100],many=True).data,
            print_campaigns=list(PrintCampaign.objects.values('id','title','source')[:100]),
            participants=list(InvitationLink.objects.annotate(count=Count('invitationregistration__invitationconversion',distinct=True),registrations=Count('invitationregistration',distinct=True)).order_by('-created_at').values('token','owner_id','campaign_id','count','registrations')[:200]),
            rewards=list(InvitationReward.objects.order_by('-pk').values('id','link__owner_id','kind','threshold','quantity','issued_at')[:200]),
            audit=list(InvitationAudit.objects.order_by('-pk').values()[:100])))
    @transaction.atomic
    def post(self,request):
        action=request.data.get('action')
        reason=str(request.data.get('reason','')).strip()
        if not reason or len(reason)>500: raise ValidationError('请填写操作原因（最多 500 字）')
        if action=='issue':
            if not permitted(request.user,'public_experience.add_invitationreward'): raise PermissionDenied()
            r=svc.issue(request.data.get('reward_id'),request.user,reason)
            return success_response({'id':r.pk})
        if action=='revoke_card':
            if not permitted(request.user,'ai_production.change_productionresetcard'): raise PermissionDenied()
            from ai_production.models import ProductionResetCard
            c=get_object_or_404(ProductionResetCard.objects.select_for_update(),pk=request.data.get('card_id'))
            if c.used_reset_id: raise ValidationError('已使用的卡不能撤销')
            c.revoked_at=timezone.now();c.save(update_fields=['revoked_at'])
            target=str(c.pk)
        elif action=='save':
            data=request.data.get('campaign',{})
            c=get_object_or_404(InvitationCampaign.objects.select_for_update(),pk=data['id']) if data.get('id') else None
            if c and InvitationLink.objects.filter(campaign=c).exists():
                raise ValidationError('活动已有参与者，规则不可修改；请暂停后新建活动')
            serializer=CampaignSerializer(c,data=data);serializer.is_valid(raise_exception=True)
            c=serializer.save()
            if c.active: svc.validate_campaign(c)
            target=str(c.pk)
        elif action=='automation':
            c=get_object_or_404(InvitationCampaign.objects.select_for_update(),pk=request.data.get('id'))
            c.automatic=not c.automatic;c.save(update_fields=['automatic']);target=str(c.pk)
        elif action=='toggle':
            c=get_object_or_404(InvitationCampaign.objects.select_for_update(),pk=request.data.get('id'))
            c.active=not c.active
            if c.active: svc.validate_campaign(c)
            c.save(update_fields=['active']);target=str(c.pk)
        else: raise ValidationError('未知操作')
        InvitationAudit.objects.create(actor=request.user,action=action,target=target,reason=reason)
        return success_response({'ok':True})
