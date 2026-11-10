from django.contrib.auth import get_user_model
from django.db import transaction
from django.core import signing
from django.db.models import Q, Count
from uuid import UUID
from .coupons import coupon_amount, product_scope_label
from .domain import quote
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import PrintCoupon, Product
from .domain import Conflict


class CanGrant(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_active and (request.user.has_perm('print_orders.add_printcoupon') or request.method=='GET' and request.user.has_perm('print_orders.view_printcoupon'))


class GrantInput(serializers.Serializer):
    owner = serializers.IntegerField(min_value=1)
    product = serializers.UUIDField()
    percent = serializers.ChoiceField(choices=[50, 100])
    included_pages = serializers.IntegerField(min_value=1, max_value=500)
    cap_fen = serializers.IntegerField(min_value=1, max_value=1000000)
    expires_at = serializers.DateTimeField()
    ticket = serializers.CharField(max_length=80)


class Grants(APIView):
    permission_classes = [CanGrant]

    def get(self, request):
        params=request.query_params
        rows=PrintCoupon.objects.select_related('order','product').order_by('-issued_at','pk')
        term=params.get('q','').strip()
        if term:
            match=Q(grant_key__icontains=term)
            if term.isdecimal() and len(term)<19:
                match |= Q(owner_id=int(term))
            try:
                uid=UUID(term)
                match |= Q(pk=uid)|Q(order_id=uid)
            except ValueError:
                pass
            rows=rows.filter(match)
        source=params.get('source')
        if source in ('manual','campaign','annual'):
            rows=rows.filter(grant_key__startswith=source+':')
        now=timezone.now()
        used=Q(order__payment_state__in=['paid','refunded','refund_pending'])|Q(order__payment_state='not_required',order__file_state='ready')
        states={'已使用':used,'订单占用':Q(order__isnull=False)&~used,'已到期':Q(order__isnull=True,expires_at__lte=now),
                '可用':Q(order__isnull=True,expires_at__gt=now)}
        if params.get('state') in states:
            rows=rows.filter(states[params['state']])
        page=serializers.IntegerField(min_value=1,max_value=10000000).run_validation(params.get('page',1))
        result=[]
        for c in rows[(page-1)*20:page*20]:
            kind,_,key=c.grant_key.partition(':')
            state='可用' if c.expires_at>now else '已到期'
            if c.order_id:
                state='已使用' if c.order.payment_state in ('paid','refunded','refund_pending') or c.order.payment_state=='not_required' and c.order.file_state=='ready' else '订单占用'
            result.append(dict(id=c.pk,owner_id=c.owner_id,name=c.name,product=product_scope_label(c.product),source={'annual':'年费','manual':'定向','campaign':'制作达标'}.get(kind,'其他'),
                ticket=key.partition(':')[2] if kind=='manual' else '',state=state,issued_at=c.issued_at,expires_at=c.expires_at,order_id=c.order_id))
        return Response(dict(results=result,total=rows.count(),products=list(Product.objects.filter(active=True,proof_approved=True).values('id','title','base_fen','page_fen','shipping_fen','min_pages','max_pages'))))

    @transaction.atomic
    def post(self, request):
        data = GrantInput(data=request.data)
        data.is_valid(raise_exception=True)
        d = data.validated_data
        owner = get_object_or_404(get_user_model(), pk=d['owner'], is_active=True)
        product = get_object_or_404(Product, pk=d['product'], active=True, proof_approved=True)
        if d['expires_at'] <= timezone.now():
            raise serializers.ValidationError('有效期必须晚于当前时间')
        fields = dict(owner=owner, product=product, percent=d['percent'], included_pages=d['included_pages'],
                      expires_at=d['expires_at'], cap_fen=d['cap_fen'],
                      name='标准装订抵扣券' if d['percent']==100 else '标准装订半价券')
        sample_pages=max(product.min_pages,min(d['included_pages'],product.max_pages))
        grant_key=f"manual:{owner.pk}:{d['ticket']}"
        prior=PrintCoupon.objects.filter(grant_key=grant_key).first()
        if prior and any(getattr(prior,k)!=v for k,v in fields.items()):
            raise Conflict('相同工单已发放不同配置的券')
        if prior and request.data.get('preview') is not True:
            return Response({'id':str(prior.pk),'created':False})
        if not product.regions:
            raise serializers.ValidationError('商品未配置配送地区')
        price=quote(product,sample_pages,1,product.regions[0])
        discount=coupon_amount(PrintCoupon(**fields),product,sample_pages)
        fingerprint=[request.user.pk,str(owner.pk),str(product.pk),product.revision,d['ticket'],d['percent'],
                     d['included_pages'],d['cap_fen'],d['expires_at'].isoformat(),price['total_fen'],discount]
        if request.data.get('preview') is True:
            return Response(dict(account=owner.get_username(),product=product.title,pages=sample_pages,discount=discount,
                shipping=price['shipping_fen'],production=price['production_fen'],total=price['total_fen']-discount,
                confirmation=signing.dumps(fingerprint,salt='print-coupon-preview')))
        try:
            confirmed=signing.loads(request.data.get('confirmation') or '',salt='print-coupon-preview',max_age=900)
        except signing.BadSignature:
            raise Conflict('请重新核对用户和试算金额')
        if confirmed!=fingerprint:
            raise Conflict('发放条件已变化，请重新试算')
        coupon, created = PrintCoupon.objects.get_or_create(grant_key=f"manual:{owner.pk}:{d['ticket']}", defaults=fields)
        if any(getattr(coupon, k) != v for k, v in fields.items()):
            raise Conflict('相同工单已发放不同配置的券')
        if created:
            from django.contrib.admin.models import LogEntry, ADDITION
            LogEntry.objects.log_actions(user_id=request.user.pk,queryset=[coupon],action_flag=ADDITION,
                                         change_message='定向发券工单 '+d['ticket'])
        return Response({'id': str(coupon.pk),'created':created}, status=201 if created else 200)


from .models import PrintCampaign, PrintEnrollment
from .campaigns import award, HALF_PAGE_THRESHOLD, FULL_PAGE_THRESHOLD


class ManageCampaign(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_active and request.user.has_perm('print_orders.change_printcampaign')


class CampaignForm(serializers.ModelSerializer):
    title = serializers.CharField(max_length=100, trim_whitespace=True, error_messages={
        'required': '请输入活动标题',
        'blank': '请输入活动标题',
        'max_length': '活动标题最多 100 个字',
    })

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all(), allow_null=True)

    class Meta:
        model=PrintCampaign
        fields=['id','title','source','product','annual_product_id','annual_percent','included_pages',
                'quota','cap_fen','valid_days','starts_at','ends_at','active']

    def validate(self, data):
        if data['starts_at'] >= data['ends_at'] or data['ends_at']<=timezone.now():
            raise serializers.ValidationError('请检查活动起止时间')
        if not all(data.get(k,0)>0 for k in ('quota','cap_fen','included_pages','valid_days')):
            raise serializers.ValidationError('名额、抵扣金额、包含页数和券期必须大于零')
        product = data['product']
        if product and not (product.active and product.proof_approved):
            raise serializers.ValidationError('请选择可印制的在售规格')
        if product is None and not Product.objects.filter(active=True, proof_approved=True).exists():
            raise serializers.ValidationError('请先开放至少一种印制规格')
        if data['source']=='annual' and not data.get('annual_product_id','').strip():
            raise serializers.ValidationError('请指定年费商品')
        overlap=PrintCampaign.objects.filter(active=True,source=data['source'], starts_at__lt=data['ends_at'],ends_at__gt=data['starts_at'])
        if data['source']=='annual':
            overlap=overlap.filter(annual_product_id=data['annual_product_id'])
        if data.get('active') and overlap.exists():
            raise serializers.ValidationError('同一投放范围已有时段重叠的活动')
        return data


def campaign_version(plan):
    import hashlib
    import json
    payload = json.dumps(dict(CampaignForm(plan).data), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def campaign_product_preview(data, product):
    if not product.regions:
        raise serializers.ValidationError({'product': '请先配置配送地区'})
    pages = max(product.min_pages, min(data['included_pages'], product.max_pages))
    price = quote(product, pages, 1, product.regions[0])
    rates = (50, 100) if data['source'] == 'pages' else (data.get('annual_percent', 100),)
    samples = []
    for rate in rates:
        coupon = PrintCoupon(percent=rate, included_pages=data['included_pages'], cap_fen=data['cap_fen'])
        discount = coupon_amount(coupon, product, pages)
        samples.append(dict(percent=rate, discount=discount, payable=price['total_fen']-discount))
    return dict(product=product.title, pages=pages, region=product.regions[0], production=price['production_fen'],
                shipping=price['shipping_fen'], samples=samples)


def campaign_preview(data):
    product = data['product']
    products = [product] if product else Product.objects.filter(active=True, proof_approved=True).order_by('title', 'pk')
    previews = [campaign_product_preview(data, item) for item in products]
    if not previews:
        raise serializers.ValidationError({'product': '请先开放至少一种印制规格'})
    return dict(**previews[0], maximum=data['quota']*data['cap_fen'], quotes=previews)


def participant_data(row):
    coupon = row.coupon
    order = coupon.order if coupon else None
    state = '未发放'
    if order:
        used = order.payment_state in ('paid', 'refunded', 'refund_pending') or (
            order.payment_state == 'not_required' and order.file_state == 'ready')
        state = '已使用' if used else '订单占用'
    elif coupon:
        state = '可用' if coupon.expires_at > timezone.now() else '已到期'
    history = row.participation_history or [dict(event='joined', at=row.created_at.isoformat(), book_id=row.book_id)]
    return dict(id=row.pk, owner_id=row.owner_id, username=row.owner.get_username(), book_id=row.book_id,
                created_at=row.created_at, withdrawn_at=row.withdrawn_at, reported_pages=row.reported_pages,
                approved_pages=row.approved_pages, half_threshold=HALF_PAGE_THRESHOLD, full_threshold=FULL_PAGE_THRESHOLD, review_decision=row.review_decision, review_reason=row.review_reason, coupon_id=coupon.pk if coupon else None, coupon_state=state,
                reward_completed=bool(coupon and coupon.percent==100), coupon_name=coupon.name if coupon else None, order_id=order.pk if order else None, history=history)


class CampaignConsole(APIView):
    permission_classes=[ManageCampaign]

    def get(self,request):
        now=timezone.now()
        if request.query_params.get('participants'):
            plan_id = serializers.IntegerField(min_value=1).run_validation(request.query_params['participants'])
            plan = get_object_or_404(PrintCampaign, pk=plan_id)
            rows = PrintEnrollment.objects.filter(plan=plan).select_related('owner', 'coupon__order').order_by('-created_at', '-pk')
            term = request.query_params.get('q', '').strip()
            if term:
                match = Q(owner__username__icontains=term)
                if term.isdecimal() and len(term) < 19:
                    match |= Q(owner_id=int(term))
                try:
                    match |= Q(book_id=UUID(term))
                except ValueError:
                    pass
                rows = rows.filter(match)
            status = request.query_params.get('status')
            if status in ('joined', 'withdrawn'):
                rows = rows.filter(withdrawn_at__isnull=status == 'joined')
            page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('page', 1))
            return Response(dict(title=plan.title, total=rows.count(),
                                 participants=[participant_data(row) for row in rows[(page-1)*20:page*20]]))
        if request.query_params.get('id'):
            plan = get_object_or_404(PrintCampaign, pk=request.query_params['id'])
            return Response(dict(CampaignForm(plan).data, draft=plan.draft, version=campaign_version(plan)))
        pending=PrintEnrollment.objects.filter(plan__source='pages',withdrawn_at__isnull=True,review_decision='pending').exclude(coupon__percent=100).filter(
            Q(reported_pages__gte=HALF_PAGE_THRESHOLD,approved_pages__lt=HALF_PAGE_THRESHOLD)|Q(reported_pages__gte=FULL_PAGE_THRESHOLD,approved_pages__lt=FULL_PAGE_THRESHOLD))
        pending_counts={row['plan_id']:row['count'] for row in pending.values('plan_id').annotate(count=Count('pk'))}
        plans=[]
        for plan in PrintCampaign.objects.annotate(taken=Count('printenrollment',filter=Q(printenrollment__withdrawn_at__isnull=True)|Q(printenrollment__coupon__isnull=False))).order_by('-pk')[:100]:
            state=('草稿' if plan.draft else '已结束' if plan.ends_at<=now else '已暂停' if not plan.active else '待开始' if plan.starts_at>now else
                   '已满额' if plan.taken>=plan.quota else '进行中')
            plans.append(dict(CampaignForm(plan).data,state=state,draft=plan.draft,remaining=max(0,plan.quota-plan.taken),
                              pending=pending_counts.get(plan.pk,0)))
        if request.query_params.get('review_plan'):
            plan_id=serializers.IntegerField(min_value=1).run_validation(request.query_params['review_plan'])
            pending=pending.filter(plan_id=plan_id)
        pending=pending.order_by('created_at','pk')
        page=serializers.IntegerField(min_value=1).run_validation(request.query_params.get('page',1))
        return Response(dict(plans=plans,products=list(Product.objects.filter(active=True,proof_approved=True).values('id','title')),
            half_threshold=HALF_PAGE_THRESHOLD, full_threshold=FULL_PAGE_THRESHOLD, total_pending=pending.count(),entries=list(pending[(page-1)*20:page*20].values('id','plan_id','plan__title','owner_id','book_id','reported_pages','approved_pages','created_at','attempt','coupon__percent','coupon__order_id','coupon__order__payment_state','coupon__order__file_state'))))

    @transaction.atomic
    def post(self,request):
        action=request.data.get('action')
        result_message='操作已完成'
        if action=='preview':
            form=CampaignForm(data=request.data)
            form.is_valid(raise_exception=True)
            return Response(campaign_preview(form.validated_data))
        if action=='update':
            plan=get_object_or_404(PrintCampaign.objects.select_for_update(),pk=request.data.get('id'),draft=True)
            if request.data.get('version') != campaign_version(plan):
                raise Conflict('草稿已被修改，请重新打开后再编辑')
            form=CampaignForm(plan,data=dict(request.data,active=False))
            form.is_valid(raise_exception=True)
            form.save()
        elif action=='create':
            if not request.user.has_perm('print_orders.add_printcampaign'):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied()
            form=CampaignForm(data=request.data)
            form.is_valid(raise_exception=True)
            form.save(draft=not form.validated_data.get('active',False))
        elif action=='publish':
            plan=get_object_or_404(PrintCampaign.objects.select_for_update(),pk=request.data.get('id'),draft=True)
            if request.data.get('version') != campaign_version(plan):
                raise Conflict('草稿已被修改，请重新预览')
            payload=dict(CampaignForm(plan).data,active=True,product=str(plan.product_id) if plan.product_id else None)
            form=CampaignForm(data=payload)
            form.is_valid(raise_exception=True)
            campaign_preview(form.validated_data)
            plan.active=True
            plan.draft=False
            plan.save(update_fields=['active','draft'])
        elif action=='pause':
            plan=get_object_or_404(PrintCampaign.objects.select_for_update(),pk=request.data.get('id'))
            plan.active=False
            plan.save(update_fields=['active'])
        elif action in ('return', 'reject'):
            if not request.user.has_perm('print_orders.change_printenrollment'):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied()
            row = get_object_or_404(PrintEnrollment.objects.select_for_update(), pk=request.data.get('id'), plan__source='pages')
            if row.withdrawn_at or row.attempt != request.data.get('attempt'):
                raise Conflict('报名已变化，请重新打开审核申请')
            reason = serializers.CharField(max_length=500).run_validation(request.data.get('reason'))
            pages = serializers.ListField(child=serializers.UUIDField(), max_length=100).run_validation(request.data.get('page_ids', []))
            if row.approved_pages >= min(row.reported_pages, FULL_PAGE_THRESHOLD) or row.reported_pages < HALF_PAGE_THRESHOLD:
                raise Conflict('当前申请没有待核验档位')
            row.review_decision = 'returned' if action == 'return' else 'rejected'
            row.review_reason = reason
            row.review_page_ids = [str(page) for page in pages]
            if not row.participation_history:
                row.record_participation('joined', row.created_at)
            row.record_participation(row.review_decision, timezone.now())
            row.participation_history[-1]['reason'] = reason
            row.save(update_fields=['review_decision', 'review_reason', 'review_page_ids', 'participation_history'])
            result_message = '已退回补充' if action == 'return' else '已记录未通过原因'
        elif action=='approve':
            if not request.user.has_perm('print_orders.change_printenrollment'):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied()
            row=get_object_or_404(PrintEnrollment.objects.select_for_update(),pk=request.data.get('id'),plan__source='pages')
            if row.withdrawn_at:
                raise Conflict('用户已退出活动，申请已撤回')
            if row.review_decision != 'pending':
                raise Conflict('申请已处理，等待用户重新提交')
            if request.data.get('attempt', 1) != row.attempt:
                raise Conflict('报名已变化，请重新打开审核申请')
            tier=request.data.get('tier')
            if tier not in (HALF_PAGE_THRESHOLD,FULL_PAGE_THRESHOLD) or row.reported_pages<tier:
                raise Conflict('当前进度未达此档位')
            award(row,100 if tier==FULL_PAGE_THRESHOLD else 50)
            if tier > row.approved_pages:
                if not row.participation_history:
                    row.record_participation('joined', row.created_at)
                row.approved_pages = tier
                row.record_participation('approved', timezone.now())
                row.save(update_fields=['approved_pages', 'participation_history'])
            coupon=PrintCoupon.objects.select_related('order').get(pk=row.coupon_id)
            if tier==FULL_PAGE_THRESHOLD and coupon.percent<100 and coupon.order:
                order=coupon.order
                used=order.payment_state in ('paid','refunded','refund_pending') or (
                    order.payment_state=='not_required' and order.file_state=='ready')
                result_message=(f'{FULL_PAGE_THRESHOLD} 页已核验，原半价券已使用。符合返券条件时将升级' if used
                                else f'{FULL_PAGE_THRESHOLD} 页已核验，原半价券释放后将升级')
            else:
                result_message=f'{FULL_PAGE_THRESHOLD} 页已核验，抵扣券已到账' if tier==FULL_PAGE_THRESHOLD else f'{HALF_PAGE_THRESHOLD} 页已核验，优惠券已到账'
        else:
            raise serializers.ValidationError('不支持的操作')
        from django.contrib.admin.models import LogEntry, CHANGE
        LogEntry.objects.log_actions(user_id=request.user.pk,queryset=[form.instance if action in ('create','update') else plan if action in ('pause','publish') else row],
                                     action_flag=CHANGE,change_message='印制活动：'+action)
        return Response(dict(message='操作已完成', id=form.instance.pk, version=campaign_version(form.instance)) if action in ('create','update') else dict(message=result_message))
