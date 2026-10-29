import hmac
import uuid
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .identity import bootstrap, identity_for, BillingError
from .models import *
from . import services
from .flags import enabled,client_flags

class AuthView(APIView):
    permission_classes=[IsAuthenticated]

class Bootstrap(AuthView):
    def post(self,request):
        session=bootstrap(request.user,request.data.get('signed_app_transaction'))
        return Response(dict(session_id=str(session.pk),rc_app_user_id=str(session.identity.rc_app_user_id),wallet_domain=session.identity.wallet_domain,public_key=settings.REVENUECAT_PUBLIC_KEY,expires_at=session.expires_at,flags=client_flags(session.identity)))

class Wallet(AuthView):
    def get(self,request): return Response(services.wallet(identity_for(request),refresh=True))
    def post(self,request): return self.get(request)

class Products(AuthView):
    def get(self,request):
        identity=identity_for(request)
        products=RechargeProduct.objects.filter(rc_project_id=identity.rc_project_id,state='active').order_by('units')
        return Response(dict(offering_id='diamonds',enabled=enabled('DIAMOND_RECHARGE_ENABLED',identity),items=[dict(id=str(p.pk),apple_product_id=p.apple_product_id,package_id=p.rc_package_id,units=p.units,currency=p.currency_code,configuration_revision=p.configuration_revision) for p in products]))

class Quotes(AuthView):
    def post(self,request):
        identity=identity_for(request)
        offer_id=serializers.UUIDField().run_validation(request.data.get('offer_id'))
        offer=get_object_or_404(ContentOffer,pk=offer_id)
        q=services.quote(identity,offer)
        return Response(dict(quote_id=str(q.pk),offer_id=str(offer.pk),title=offer.title,policy_revision=q.policy_revision.revision,currency='DIAMOND',diamond_price=q.quoted_units,balance=services.wallet(identity,refresh=True)['balance'],expires_at=q.expires_at,ownership='not_owned',member_access=services.has_member(identity) and q.policy_revision.access_mode=='pro_or_diamond'))

def order_json(order):
    return dict(order_id=str(order.pk),offer_id=str(order.offer_id),title=order.offer.title,status=order.status,amount=order.amount,last_error_code=order.last_error_code,retry_after_seconds=3,can_retry_purchase=order.status=='rejected',created_at=order.created_at)

class Redemptions(AuthView):
    def get(self,request,pk=None):
        qs=RedemptionOrder.objects.filter(identity=identity_for(request)).select_related('offer').order_by('-created_at')
        if pk: return Response(order_json(get_object_or_404(qs,pk=pk)))
        if request.query_params.get('state')=='pending': qs=qs.exclude(status__in=services.TERMINAL)
        return Response(dict(items=[order_json(o) for o in qs[:100]]))
    def post(self,request):
        identity=identity_for(request)
        quote_id=serializers.UUIDField().run_validation(request.data.get('quote_id'))
        offer_id=serializers.UUIDField().run_validation(request.data.get('offer_id'))
        order=services.prepare(identity,quote_id,offer_id,request.headers.get('Idempotency-Key'))
        if order.status not in services.TERMINAL:
            op=order.operations.filter(kind='debit').first()
            if op: services.process(op.pk)
            order.refresh_from_db()
        return Response(order_json(order),status=200 if order.status in services.TERMINAL else 202)

class Ownerships(AuthView):
    def get(self,request):
        qs=ContentOwnership.objects.filter(identity=identity_for(request),state='active').order_by('-created_at')
        return Response(dict(items=[dict(id=str(o.pk),target_kind=o.target_kind,target_id=str(o.target_id),source_kind=o.source_kind,granted_at=o.created_at) for o in qs[:500]]))

class Entries(AuthView):
    def get(self,request):
        qs=WalletLedgerEntry.objects.filter(identity=identity_for(request)).order_by('-id')
        cursor=serializers.IntegerField(min_value=1,required=False).run_validation(request.query_params['cursor']) if request.query_params.get('cursor') else None
        if cursor: qs=qs.filter(id__lt=cursor)
        rows=list(qs[:41])
        return Response(dict(items=[dict(id=str(e.pk),delta=e.delta,title=e.title,entry_kind=e.entry_kind,order_id=str(e.order_id) if e.order_id else None,created_at=e.created_at) for e in rows[:40]],next_cursor=str(rows[39].pk) if len(rows)>40 else None))

class Webhook(APIView):
    authentication_classes=[]
    permission_classes=[AllowAny]
    def post(self,request):
        expected=settings.REVENUECAT_WEBHOOK_AUTH
        if not expected or not hmac.compare_digest(request.headers.get('Authorization',''),expected):
            return Response(status=401)
        if not isinstance(request.data,dict): return Response(status=400)
        event=request.data.get('event',{})
        if not isinstance(event,dict) or not isinstance(event.get('id'),str) or len(event['id'])>150:
            return Response(status=400)
        if event.get('type')=='TEST': return Response({'received':True})
        if event.get('app_id')!=settings.REVENUECAT_APP_ID: return Response(status=403)
        if getattr(self,'sandbox_only',False) and event.get('purchase_environment',event.get('environment'))!='SANDBOX':
            return Response(status=403)
        # Persist authenticated events before processing, including unknown identities.
        obj,_=CurrencyEvent.objects.get_or_create(event_id=settings.REVENUECAT_PROJECT_ID+':'+event['id'],defaults={'payload':event})
        from .tasks import process_event
        process_event(obj.pk)
        return Response({'received':True})

class ContentAccess(AuthView):
    def get(self,request,kind,pk):
        if kind not in ('template','sticker_library','font'): return Response(status=404)
        if kind == 'font':
            from font_library.models import FontFamily
            from font_library.services import access
            from django.shortcuts import get_object_or_404
            return Response(access(request,get_object_or_404(FontFamily,pk=pk)))
        from .access import describe
        return Response(describe(request,kind,pk))

class CustomizationPayment(AuthView):
    def get(self,request,pk):
        from diary_customizations.models import Request
        obj=get_object_or_404(Request,pk=pk,owner=request.user,deleted_at__isnull=True)
        identity=identity_for(request)
        quote=obj.billing_quotes.order_by('-revision').first()
        funding=obj.diamond_fundings.filter(identity=identity).order_by('-created_at').first()
        if not quote: return Response({'quote':None,'funding':None})
        pro=services.has_member(identity) and quote.pro_diamonds is not None
        return Response({'quote':dict(quote_id=str(quote.pk),quote_revision=quote.revision,expected_request_revision=quote.expected_request_revision,total_diamonds=quote.pro_diamonds if pro else quote.standard_diamonds,standard_diamonds=quote.standard_diamonds,pricing_reason='pro' if pro else 'standard',scope=quote.scope_snapshot,expires_at=quote.expires_at),'funding':dict(id=str(funding.pk),status=funding.status,amount=funding.amount) if funding else None,'enabled':enabled('DIAMOND_CUSTOMIZATION_ENABLED',identity)})
    def post(self,request,pk):
        from .customization import prepare_funding
        from diary_customizations.models import Request
        get_object_or_404(Request,pk=pk,owner=request.user,deleted_at__isnull=True)
        identity=identity_for(request)
        class Input(serializers.Serializer):
            quote_id=serializers.UUIDField()
            quote_revision=serializers.IntegerField(min_value=1)
            expected_request_revision=serializers.IntegerField(min_value=1)
            expected_total=serializers.IntegerField(min_value=1)
        form=Input(data=request.data);form.is_valid(raise_exception=True)
        key=serializers.UUIDField().run_validation(request.headers.get('Idempotency-Key'))
        data=form.validated_data
        services.refresh_membership(identity,force=True)
        funding=prepare_funding(identity,pk,data['quote_id'],data['quote_revision'],data['expected_request_revision'],key,data['expected_total'])
        operation=funding.operations.filter(kind='debit').first()
        if operation: services.process(operation.pk)
        funding.refresh_from_db()
        return Response({'id':str(funding.pk),'status':funding.status,'amount':funding.amount},status=200 if funding.status in ('funded','refunded','rejected','price_changed') else 202)

class SandboxWebhook(Webhook):
    sandbox_only=True

class Membership(AuthView):
    def get(self, request):
        from .membership import status
        return Response(status(identity_for(request)))
    def post(self, request):
        from .membership import status
        return Response(status(identity_for(request), force=True))
