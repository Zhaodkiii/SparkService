from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import PrintCampaign, PrintEnrollment, PrintCoupon, Product
from .domain import Conflict
from .coupons import coupon_amount, product_scope_label


HALF_PAGE_THRESHOLD = 20
FULL_PAGE_THRESHOLD = 40


def open_plans(source, at):
    scope = Q(product__active=True, product__proof_approved=True)
    if Product.objects.filter(active=True, proof_approved=True).exists():
        scope |= Q(product__isnull=True)
    return PrintCampaign.objects.filter(source=source, active=True, starts_at__lte=at, ends_at__gt=at).filter(scope).order_by('-pk')

def occupied_enrollments(plan):
    return PrintEnrollment.objects.filter(plan=plan).filter(Q(withdrawn_at__isnull=True) | Q(coupon__isnull=False))


def reserve(plan, owner, book_id=None):
    entry = PrintEnrollment.objects.select_for_update().filter(plan=plan, owner=owner).first()
    if entry and not entry.withdrawn_at:
        if entry.book_id != book_id:
            raise Conflict('本活动已绑定另一本手帐')
        return entry
    if entry and entry.coupon_id:
        raise Conflict('本期已领券，退出后不能再次报名')
    if occupied_enrollments(plan).count() >= plan.quota:
        raise Conflict('本期活动名额已满')
    if not entry:
        return PrintEnrollment.objects.create(plan=plan, owner=owner, book_id=book_id)
    if not entry.participation_history:
        entry.record_participation('joined', entry.created_at)
    entry.book_id = book_id
    entry.reported_pages = 0
    entry.approved_pages = 0
    entry.withdrawn_at = None
    entry.review_decision = 'pending'
    entry.review_reason = ''
    entry.review_page_ids = []
    entry.attempt += 1
    entry.record_participation('joined', timezone.now())
    entry.save(update_fields=['book_id', 'reported_pages', 'approved_pages', 'withdrawn_at', 'attempt', 'participation_history', 'review_decision', 'review_reason', 'review_page_ids'])
    return entry


def reward_name(plan, percent):
    product = plan.product
    if product and not product.free_printing:
        base = product.base_fen + product.page_fen * plan.included_pages
        discount = min(plan.cap_fen, base * percent // 100)
        if percent == 100 and discount == base:
            return '标准装订免费券'
        if percent == 50 and discount == base // 2:
            return '标准装订半价券'
    return f'标准装订抵扣券（最高 ¥{plan.cap_fen / 100:.2f}）'


def award(entry, percent):
    plan = entry.plan
    if entry.coupon_id:
        coupon = PrintCoupon.objects.select_for_update().get(pk=entry.coupon_id)
        if coupon.order_id or coupon.percent >= percent:
            return
        coupon.percent = percent
        coupon.name = reward_name(plan, percent)
        coupon.save(update_fields=['percent','name'])
        return
    entry.coupon = PrintCoupon.objects.create(owner=entry.owner, product=plan.product,
        name=reward_name(plan, percent),
        percent=percent, cap_fen=plan.cap_fen, included_pages=plan.included_pages,
        grant_key=f'campaign:{entry.pk}', expires_at=max(plan.ends_at,timezone.now()+timedelta(days=plan.valid_days)))
    entry.save(update_fields=['coupon'])


def enrollment_data(entry):
    if not entry:
        return None
    coupon = entry.coupon
    return dict(reported_pages=entry.reported_pages, approved_pages=entry.approved_pages,
                withdrawn_at=entry.withdrawn_at, attempt=entry.attempt,
                coupon_percent=coupon.percent if coupon else None,
                coupon_available=bool(coupon and not coupon.order_id and coupon.expires_at>timezone.now()))


def book_experience(plan, entry, local_pages=0, blocked=None):
    now = timezone.now()
    active_period = plan.starts_at <= now < plan.ends_at
    coupon = entry.coupon if entry else None
    order = coupon.order if coupon else None
    used = bool(order and (order.transaction_id or order.payment_state == 'not_required' and order.file_state == 'ready'))
    available = bool(coupon and not order and coupon.expires_at > now)
    reported = entry.reported_pages if entry else 0
    approved = entry.approved_pages if entry else 0
    progress = min(max(reported, local_pages), FULL_PAGE_THRESHOLD) / FULL_PAGE_THRESHOLD if entry and not entry.withdrawn_at else 0
    status, heading, detail, action, label = 'available', '制作手帐领装订优惠', f'满 {HALF_PAGE_THRESHOLD} 个有效内页可申请第一档奖励', 'join', '用这本参加'
    if blocked:
        status, heading, detail, action, label = 'unavailable', '活动暂不可报名', blocked, 'close', '返回作品'
    if entry:
        status, heading, detail, action, label = 'making', '本册装订礼', f'已申报 {reported} 页，距下一档还差 {max(0, (HALF_PAGE_THRESHOLD if reported < HALF_PAGE_THRESHOLD else FULL_PAGE_THRESHOLD)-max(reported,local_pages))} 页', 'continue', '继续制作'
        if reported >= HALF_PAGE_THRESHOLD and approved < HALF_PAGE_THRESHOLD:
            status, heading, detail = 'half_pending', '第一档核验中', f'已提交 {reported} 页，可继续制作冲击 {FULL_PAGE_THRESHOLD} 页档'
        if reported >= FULL_PAGE_THRESHOLD and approved < FULL_PAGE_THRESHOLD:
            status, heading, detail, label = 'full_pending', f'{FULL_PAGE_THRESHOLD} 页档核验中', f'已提交 {reported} 页，等待核验', '返回作品'
        if coupon and coupon.percent == 50:
            status, heading, detail, action, label = 'half_ready', '第一档优惠券已到账', f'继续制作可申请 {FULL_PAGE_THRESHOLD} 页档', 'continue', f'继续做到 {FULL_PAGE_THRESHOLD} 页'
        if reported >= FULL_PAGE_THRESHOLD and approved < FULL_PAGE_THRESHOLD:
            status, heading, detail = 'full_pending', f'{FULL_PAGE_THRESHOLD} 页档核验中', f'已提交 {reported} 页，等待核验'
        if available and coupon.percent == 100:
            status, heading, detail, action, label = 'full_ready', '装订抵扣券已到账', '使用本券定制这本手帐', 'checkout', '用券定制'
        if coupon and not order and coupon.expires_at <= now:
            status, heading, detail, action, label = 'expired', '活动优惠券已到期', '可继续查看印制规格与价格', 'checkout', '预览并定制'
        if order:
            status, heading, detail, action, label = 'used' if used else 'locked', '本期奖励已使用' if used else '优惠券被订单占用', '在原订单查看印制与付款进度', 'order', '查看原订单'
            if approved >= FULL_PAGE_THRESHOLD and coupon.percent < 100 and not used:
                status, heading, detail = 'upgrade_waiting', f'{FULL_PAGE_THRESHOLD} 页已核验', '原半价券释放后将升级'
        next_tier = FULL_PAGE_THRESHOLD if approved >= HALF_PAGE_THRESHOLD or reported >= HALF_PAGE_THRESHOLD else HALF_PAGE_THRESHOLD
        if active_period and not order and (not coupon or coupon.percent < 100) and local_pages >= next_tier and reported < next_tier:
            status, heading, detail, action, label = 'submit_full' if next_tier == FULL_PAGE_THRESHOLD else 'submit_half', f'本册可申报 {next_tier} 页档', '提交后由运营核验有效内页', 'submit', f'提交 {next_tier} 页档核验'
        if entry.review_decision in ('returned', 'rejected') and active_period and not order:
            status = entry.review_decision
            heading = '请补充作品内容' if status == 'returned' else '本次核验未通过'
            detail, action, label = entry.review_reason, 'rework', '去完善作品'
        if entry.withdrawn_at:
            status, heading, detail, action, label = 'withdrawn', '已退出活动', '已发券可在券包查看' if coupon else '活动开放且有名额时可以重新报名', 'wallet' if coupon else 'rejoin', '查看优惠券' if coupon else '重新报名'
            progress = 0
            if blocked and not coupon:
                action, label, detail = 'close', '返回作品', blocked
        elif not active_period and not coupon:
            status, heading, detail, action, label = 'ended', '活动已结束', '保留本次报名与核验记录', 'checkout', '预览并定制'
    product = plan.product
    rewards = []
    for threshold, percent in ((HALF_PAGE_THRESHOLD, 50), (FULL_PAGE_THRESHOLD, 100)):
        amount = coupon_amount(PrintCoupon(percent=percent, included_pages=plan.included_pages, cap_fen=plan.cap_fen), product, plan.included_pages) if product else None
        text = f'装订抵扣 ¥{amount/100:.2f}' if amount is not None else f'装订抵扣 · 最高 ¥{plan.cap_fen/100:.2f}'
        rewards.append(dict(threshold=threshold, title=text, discount_fen=amount))
    events = entry.participation_history if entry else []
    token = ':'.join(map(str, [plan.pk, plan.active, plan.ends_at.isoformat(), status, approved, entry.review_reason if entry else '',
                               coupon.pk if coupon else '', coupon.percent if coupon else '', order.pk if order else '']))
    return dict(status=status, heading=heading, detail=detail, action=action, action_title=label,
                progress=progress, pending=status in ('half_pending', 'full_pending'), completed=approved >= FULL_PAGE_THRESHOLD or bool(coupon and coupon.percent == 100),
                coupon_id=str(coupon.pk) if coupon else None, product_id=str(coupon.product_id) if coupon and coupon.product_id else None, coupon_available=available,
                order_id=str(order.pk) if order else None, result_key=token,
                coupon_expires_at=coupon.expires_at if coupon else None,
                review_page_ids=entry.review_page_ids if entry else [],
                can_resubmit=bool(entry and not entry.withdrawn_at and active_period and not order
                                  and entry.review_decision in ('returned', 'rejected')),
                updated_at=events[-1].get('at') if events else (entry.created_at if entry else None),
                history=events, rewards=rewards, historical=not active_period,
                can_update=bool(entry and not entry.withdrawn_at and active_period and not order
                                and (not coupon or coupon.percent < 100) and local_pages > reported),
                can_withdraw=bool(entry and not entry.withdrawn_at))


class Placement(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now=timezone.now()
        book=request.query_params.get('book')
        existing=None
        if book:
            field=serializers.UUIDField()
            existing=PrintEnrollment.objects.filter(owner=request.user,book_id=field.run_validation(book),plan__source='pages',
                ).select_related('plan__product','coupon__order').order_by('-pk').first()
        current = open_plans('pages', now).first()
        plan = existing.plan if existing and not existing.withdrawn_at and existing.plan.ends_at > now else current
        if existing and (not current or existing.plan_id == current.pk):
            plan = existing.plan
        if not plan and existing:
            plan = existing.plan
        if not plan:
            return Response(dict(experience=dict(status='no_activity', heading='把这本手帐印成书',
                detail='选择规格，预览成品后确认费用', action='checkout', action_title='预览并定制',
                progress=0, pending=False, completed=False, result_key='', rewards=[], history=[],
                can_update=False, can_withdraw=False, historical=False)))
        enrolled = (existing if existing and existing.plan_id == plan.pk else None) or PrintEnrollment.objects.filter(plan=plan, owner=request.user).select_related('coupon').first()
        another_book = bool(enrolled and book and str(enrolled.book_id).lower() != book.lower())
        if enrolled and enrolled.withdrawn_at:
            if enrolled.coupon_id:
                blocked = '本期已领券，退出后不能再次报名'
            elif not (plan.starts_at <= now < plan.ends_at):
                blocked = '本活动已结束'
            elif not plan.active:
                blocked = '本活动已暂停招募'
            else:
                blocked = '本期活动名额已满' if occupied_enrollments(plan).count() >= plan.quota else None
        elif another_book:
            blocked = '本活动已绑定另一本手帐'
        else:
            blocked = '本期活动名额已满' if not enrolled and occupied_enrollments(plan).count() >= plan.quota else None
        local_pages = serializers.IntegerField(min_value=0, max_value=5000).run_validation(request.query_params.get('pages', 0))
        visible_entry = enrolled if not another_book or enrolled.withdrawn_at else None
        experience = book_experience(plan, visible_entry, local_pages, blocked)
        standard = PrintCoupon(percent=100, included_pages=plan.included_pages, cap_fen=plan.cap_fen)
        product = plan.product
        discount = coupon_amount(standard, product, plan.included_pages) if product else None
        covered = bool(product and discount and discount == product.base_fen + product.page_fen * plan.included_pages)
        previous = []
        if book:
            old_entries = PrintEnrollment.objects.filter(owner=request.user, book_id=book, plan__source='pages').exclude(plan=plan).select_related('plan__product', 'coupon__order').order_by('-pk')
            for old in old_entries:
                state = book_experience(old.plan, old)
                previous.append(dict(title=old.plan.title, heading=state['heading'], detail=state['detail']))
        return Response(dict(id=plan.pk,title=plan.title,cap_fen=plan.cap_fen,included_pages=plan.included_pages,
                             product=product_scope_label(plan.product),ends_at=plan.ends_at, enrollment=enrollment_data(enrolled) if not another_book or enrolled.withdrawn_at else None,
                             blocked_reason=blocked,
                             standard_discount_fen=discount,
                             standard_is_covered=covered, unrestricted=product is None, experience=experience, previous_campaigns=previous))


class Enroll(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        from .views import identity_required
        identity_required(request.user)
        class Input(serializers.Serializer):
            book_id = serializers.UUIDField()
            pages = serializers.IntegerField(min_value=0,max_value=5000)
            rejoin = serializers.BooleanField(default=False)
            attempt = serializers.IntegerField(min_value=1, default=1)
        data=Input(data=request.data)
        data.is_valid(raise_exception=True)
        now=timezone.now()
        plan=PrintCampaign.objects.select_for_update().filter(pk=pk,source='pages',starts_at__lte=now,ends_at__gt=now).first()
        if plan and not plan.active and not PrintEnrollment.objects.filter(plan=plan,owner=request.user,withdrawn_at__isnull=True).exists():
            plan=None
        if not plan:
            raise Conflict('活动已结束')
        previous = PrintEnrollment.objects.select_for_update().filter(plan=plan, owner=request.user).first()
        if previous:
            if previous.attempt != data.validated_data['attempt']:
                if (data.validated_data['rejoin'] and not previous.withdrawn_at
                    and previous.attempt == data.validated_data['attempt'] + 1
                    and previous.book_id == data.validated_data['book_id']):
                    return Response(dict(message='已重新报名', enrollment=enrollment_data(previous)))
                raise Conflict('报名已变化，请重新打开活动')
            if previous.withdrawn_at and not data.validated_data['rejoin']:
                raise Conflict('已退出活动，请重新报名')
        row=reserve(plan,request.user,data.validated_data['book_id'])
        pages = data.validated_data['pages']
        resubmission = row.review_decision in ('returned', 'rejected')
        if resubmission:
            row.review_decision = 'pending'
            row.review_reason = ''
            row.review_page_ids = []
        if pages != row.reported_pages or resubmission:
            if not row.participation_history:
                row.record_participation('joined', row.created_at)
            row.reported_pages = pages
            row.record_participation('progress', timezone.now())
            row.save(update_fields=['reported_pages', 'participation_history', 'review_decision', 'review_reason', 'review_page_ids'])
        message = '申请已登记，达标后由运营审核发券' if row.reported_pages >= HALF_PAGE_THRESHOLD else '已报名，请继续制作并更新进度'
        return Response(dict(message=message, enrollment=enrollment_data(row)))


class Withdraw(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        class Input(serializers.Serializer):
            book_id = serializers.UUIDField()
            attempt = serializers.IntegerField(min_value=1)

        data = Input(data=request.data)
        data.is_valid(raise_exception=True)
        plan = get_object_or_404(PrintCampaign.objects.select_for_update(), pk=pk, source='pages')
        entry = get_object_or_404(PrintEnrollment.objects.select_for_update(), plan=plan, owner=request.user,
                                  book_id=data.validated_data['book_id'])
        if entry.attempt != data.validated_data['attempt']:
            raise Conflict('报名已变化，请重新打开活动')
        if not entry.withdrawn_at:
            if not entry.participation_history:
                entry.record_participation('joined', entry.created_at)
            entry.withdrawn_at = timezone.now()
            entry.record_participation('withdrawn', entry.withdrawn_at)
            entry.save(update_fields=['withdrawn_at', 'participation_history'])
        return Response(dict(message='已退出，已发券仍可在券包查看' if entry.coupon_id else '已退出活动',
                             enrollment=enrollment_data(entry)))


def annual_gift(identity, data):
    from billing.reporting import stamp
    from billing.models import StorePayment
    import hashlib
    tx=data.get('transaction_id')
    if not isinstance(tx,str) or not tx:
        return
    digest=hashlib.sha256(f'{identity.rc_project_id}:{data.get("app_id")}:{identity.wallet_domain}:APP_STORE:{tx}'.encode()).hexdigest()
    if identity.state!='active' or identity.wallet_domain!='production' or data.get('store')!='APP_STORE':
        return
    if data.get('type')=='CANCELLATION' and data.get('cancel_reason')=='CUSTOMER_SUPPORT':
        PrintCoupon.objects.filter(grant_key='annual:'+digest, owner=identity.account).update(expires_at=timezone.now())
        return
    if StorePayment.objects.filter(identity=identity, transaction_digest=digest,refund_state='refunded').exists():
        return
    if not (data.get('type')=='INITIAL_PURCHASE' or data.get('type')=='RENEWAL' and data.get('is_trial_conversion') is True) or data.get('period_type')=='TRIAL' or 'member' not in (data.get('entitlement_ids') or []):
        return
    try:
        price=Decimal(str(data.get('price_in_purchased_currency')))
        if not price.is_finite() or price<=0:
            return
    except InvalidOperation:
        return
    when=stamp(data.get('purchased_at_ms'))
    if not when or not data.get('transaction_id'):
        return
    if PrintCoupon.objects.filter(grant_key='annual:'+digest).exists():
        return
    promised=PrintEnrollment.objects.filter(owner=identity.account, plan__source='annual',
        plan__annual_product_id=data.get('product_id'), plan__starts_at__lte=when,plan__ends_at__gt=when,
        coupon__isnull=True,created_at__lte=when).order_by('-pk').first()
    plan=PrintCampaign.objects.select_for_update().get(pk=promised.plan_id) if promised else open_plans('annual',when).select_for_update().filter(annual_product_id=data.get('product_id')).first()
    if not plan:
        return
    existing = PrintEnrollment.objects.filter(plan=plan,owner=identity.account).first()
    if existing:
        if not existing.coupon_id:
            award(existing,plan.annual_percent)
            PrintCoupon.objects.filter(pk=existing.coupon_id).update(grant_key="annual:"+digest)
        return
    if PrintEnrollment.objects.filter(plan=plan).count() < plan.quota:
        entry=reserve(plan,identity.account)
        award(entry,plan.annual_percent)
        PrintCoupon.objects.filter(pk=entry.coupon_id).update(grant_key="annual:"+digest)

class AnnualOffer(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        plan = open_plans('annual',timezone.now()).first()
        if not plan:
            return Response({})
        enrollment=PrintEnrollment.objects.filter(plan=plan,owner=request.user).first()
        if (enrollment and enrollment.coupon_id) or (not enrollment and PrintEnrollment.objects.filter(plan=plan).count()>=plan.quota):
            return Response({})
        return Response(dict(id=plan.pk,title=plan.title,sku=plan.annual_product_id,
            percent=plan.annual_percent,cap_fen=plan.cap_fen,product=product_scope_label(plan.product)))

    @transaction.atomic
    def post(self,request):
        from .views import identity_required
        identity_required(request.user)
        class Input(serializers.Serializer):
            plan_id=serializers.IntegerField(min_value=1)
            sku=serializers.CharField(max_length=200)
            cancelled=serializers.BooleanField(required=False,default=False)
        data=Input(data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data['cancelled']:
            plan=PrintCampaign.objects.select_for_update().filter(pk=data.validated_data['plan_id'],source='annual',
                annual_product_id=data.validated_data['sku']).first()
            if plan:
                PrintEnrollment.objects.filter(plan=plan,owner=request.user,coupon_id__isnull=True).delete()
            return Response(dict(message='已取消预留'))
        plan=open_plans('annual',timezone.now()).select_for_update().filter(pk=data.validated_data['plan_id'],
            annual_product_id=data.validated_data['sku']).first()
        if not plan:
            raise Conflict('赠券活动已变更，请刷新会员页')
        reserve(plan,request.user)
        return Response(dict(message='已预留赠礼'))


class Wallet(APIView):
    permission_classes=[IsAuthenticated]

    def get(self,request):
        rows=PrintCoupon.objects.filter(owner=request.user).select_related('order','product').order_by('-issued_at')
        now=timezone.now()
        return Response([dict(id=str(c.pk),name=c.name,product=product_scope_label(c.product),cap_fen=c.cap_fen,
            expires_at=c.expires_at, state=('已使用' if c.order and (c.order.transaction_id or
            c.order.payment_state=='not_required' and c.order.file_state=='ready') else '订单已占用') if c.order_id
            else '已过期' if c.expires_at<=now else '可用') for c in rows])
