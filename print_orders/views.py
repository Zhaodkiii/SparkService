import json
import uuid
import secrets
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Product, Order, Production, Event, Shipment, Receipt, FileCleanup
from .domain import OrderInput, Conflict, Unavailable, spec, quote, digest, validate_manifest
from .services import event, cancel, reconcile
from . import storage, wechat
from .operations import capabilities, can_download, operate, CHECKLISTS


class PrintAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_active and
                    (request.user.is_superuser or request.user.has_perm('print_orders.change_order')))


def product_data(obj):
    return dict(**spec(obj), active=obj.active, proof_approved=obj.proof_approved,
                proof_note=obj.proof_note, proof_at=obj.proof_at, proof_by=obj.proof_by)


def actions(o, admin=False):
    result = []
    if o.state in ('draft', 'awaiting_review', 'queued', 'needs_revision'): result.append('cancel')
    if o.state == 'draft' and o.file_state == 'ready' and o.payment_state == 'unpaid' and o.total_fen > 0: result.append('pay')
    if o.state == 'draft' and o.file_state in ('uploading', 'failed'): result.append('upload')
    if o.state == 'shipped': result.append('receive')
    if o.transaction_id or (o.payment_state == 'not_required' and o.state != 'cancelled'): result.append('after_sale')
    if o.state == 'needs_revision' and not o.cancel_requested: result.append('revise')
    if admin and o.payment_state in ('paid', 'not_required') and not o.cancel_requested:
        result += {'awaiting_review':['approve','needs_revision'], 'queued':['start','needs_revision'],
                   'producing':['finish'], 'ready_to_ship':['ship']}.get(o.state, [])
    return result


def order_data(o, admin=False, user=None, summary=False):
    p = o.current_production
    result = dict(id=str(o.id), number=o.id.hex.upper(), title=o.title, spec=o.spec,
        address=o.address, quantity=o.quantity, page_count=o.page_count, total_fen=o.total_fen,
        file_state=o.file_state, payment_state=o.payment_state, state=o.state, revision=o.revision,
        allowed_actions=capabilities(o, user) if admin and user else actions(o), created_at=o.created_at.isoformat(),
        source_book_id=o.snapshot.get('book_id'), production_id=str(p.id) if p else None,
        production_number=p.number if p else 0, production_error=p.error if p else '',
        exception_reason=o.exception_reason, after_sale_state=o.after_sale_state,
        after_sale_message=o.after_sale_message, after_sale_resolution=o.after_sale_resolution,
        refund_state=o.refund_state, refund_reason=o.refund_reason,
        stage_started_at=o.stage_started_at.isoformat(), updated_at=o.updated_at.isoformat(),
        sheets_per_copy=(o.page_count+1)//2 if o.spec.get('duplex') else o.page_count,
        checks=p.result.get('checks', []) if p else [],
        can_download=can_download(o, user) if admin and user else False,
        checklists=CHECKLISTS if admin else {})
    if not summary:
        result['events'] = [dict(id=e.id, action=e.action, message=e.message, created_at=e.created_at,
            actor=(e.actor.get_username() if e.actor else '系统') if admin else ('工作人员' if e.actor_id and e.actor_id != o.owner_id else '本人' if e.actor_id else '系统'),
            details=e.details) for e in o.events.select_related('actor').order_by('id')]
        result['shipments'] = list(o.shipments.order_by('id').values('id','carrier','tracking_number','created_at','updated_at','kind'))
    return result


def json_clean(data):
    return json.loads(json.dumps(data, default=str))


def identity_required(user):
    # 设备账户不接受实体订单；使用项目 SocialIdentity 的实际账户绑定标记。
    from accounts.models import SocialIdentity
    if not user.is_superuser and not SocialIdentity.objects.filter(user=user).exclude(provider='device').exists():
        raise ValidationError('请先在设置中绑定手机号或邮箱，再提交印制订单')


class Products(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response([product_data(p) for p in Product.objects.filter(active=True, proof_approved=True)])


class Quote(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        class Input(serializers.Serializer):
            product_id = serializers.UUIDField()
            page_count = serializers.IntegerField(min_value=1, max_value=500)
            quantity = serializers.IntegerField(min_value=1, max_value=100)
            region = serializers.CharField(max_length=120)
        s = Input(data=request.data); s.is_valid(raise_exception=True); d = s.validated_data
        p = get_object_or_404(Product, pk=d['product_id'])
        return Response(dict(**quote(p, d['page_count'], d['quantity'], d['region']), product_revision=p.revision))


class Orders(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = Order.objects.filter(owner=request.user).select_related('current_production')
        if request.query_params.get('book_id'): qs = qs.filter(snapshot__book_id=request.query_params['book_id'])
        if request.query_params.get('state'): qs = qs.filter(state=request.query_params['state'])
        offset = max(0, min(int(request.query_params.get('offset','0')) if request.query_params.get('offset','0').isdigit() else 0, 100000))
        return Response(dict(results=[order_data(o) for o in qs[offset:offset+30]], next_offset=offset+30 if qs.count()>offset+30 else None))

    @transaction.atomic
    def post(self, request):
        identity_required(request.user)
        s = OrderInput(data=request.data); s.is_valid(raise_exception=True)
        d = json_clean(s.validated_data); fingerprint = digest(d)
        if d.get('revise_order_id'):
            return self.revise(request, d)
        # 锁定用户行，序列化同一用户重试/并发建单。
        type(request.user).objects.select_for_update().get(pk=request.user.pk)
        old = Order.objects.filter(owner=request.user, creation_key=d['key']).first()
        if old:
            if old.request_hash != fingerprint: raise Conflict('同一下单请求不能更换内容')
            return Response(order_data(old))
        p = get_object_or_404(Product.objects.select_for_update(), pk=d['product_id'])
        if p.revision != d['product_revision']: raise Conflict('商品规格已更新，请重新准备生产稿')
        q = quote(p, d['page_count'], d['quantity'], d['address']['region'])
        if q['total_fen'] != d['quote_total_fen']: raise Conflict('报价已更新，请重新确认')
        validate_manifest(d)
        inner = sum(page['role']=='interior' for page in d['snapshot']['pages'])
        if d['page_count'] != inner + (inner % 2 if p.duplex else 0):
            raise ValidationError('单双面补白规则不匹配')
        o = Order.objects.create(owner=request.user, product=p, creation_key=d['key'], request_hash=fingerprint,
            title=d['title'], spec=spec(p), address=d['address'], snapshot=d['snapshot'],
            quantity=d['quantity'], page_count=d['page_count'], total_fen=q['total_fen'], payment_state='not_required' if q['total_fen']==0 else 'unpaid')
        prod = Production.objects.create(order=o, manifest=d['files'], confirmed_hash=digest(d['files']))
        o.current_production = prod; o.save()
        Event.objects.create(order=o, actor=request.user, action='created', message='订单已创建，等待上传生产文件')
        return Response(order_data(o), status=201)

    def revise(self, request, d):
        o = get_object_or_404(Order.objects.select_for_update(), pk=d['revise_order_id'], owner=request.user)
        if duplicate(o, d): return Response(order_data(o))
        if o.state != 'needs_revision' or o.cancel_requested: raise Conflict('此订单当前不能修改重提')
        if d.get('order_revision') != o.revision: raise Conflict()
        if (d['product_id'] != o.spec['id'] or d['page_count'] != o.page_count or d['quantity'] != o.quantity
                or d['quote_total_fen'] != o.total_fen or d['snapshot']['book_id'] != o.snapshot['book_id']):
            raise ValidationError('重提须保持原作品、规格、内页面数和份数；如需调整，请取消后重新下单')
        validate_manifest(d)
        inner = sum(x['role'] == 'interior' for x in d['snapshot']['pages'])
        if d['page_count'] != inner + (inner % 2 if o.spec['duplex'] else 0): raise ValidationError('单双面补白规则不匹配')
        # 当前开发阶段只维护最新稿件。更换生产标识使旧链接和并发上传不能用于新稿。
        old = o.current_production
        prod = Production.objects.create(order=o, number=old.number+1, manifest=d['files'], confirmed_hash=digest(d['files']))
        o.current_production = prod; o.snapshot = d['snapshot']; o.title = d['title']; o.file_state = 'uploading'; o.state = 'draft'
        o.exception_reason = ''; event(o, 'resubmitted', '已重新提交生产稿，等待上传与审核', request.user)
        FileCleanup.objects.create(keys=storage.obsolete_keys(old))
        old.delete()
        receipt(o, d)
        return Response(order_data(o))


class Detail(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, pk):
        return Response(order_data(get_object_or_404(Order, pk=pk, owner=request.user)))


class Upload(APIView):
    permission_classes = [IsAuthenticated]
    @transaction.atomic
    def post(self, request, pk):
        o = get_object_or_404(Order.objects.select_for_update(), pk=pk, owner=request.user)
        if 'upload' not in actions(o): raise Conflict('当前订单不能上传')
        p = o.current_production
        if request.data.get('production_id') != str(p.id): raise Conflict('上传任务已过期，请使用最新生产稿')
        if p.state == 'failed':
            p.state='uploading'; p.error=''; p.uploads={}; p.save()
            o.file_state='uploading'; event(o,'retry','重新上传生产文件',request.user)
        return Response(dict(production_id=str(p.id), files=storage.multipart_plan(p)))


class CompleteUpload(APIView):
    permission_classes = [IsAuthenticated]
    @transaction.atomic
    def post(self, request, pk):
        o = get_object_or_404(Order.objects.select_for_update(), pk=pk, owner=request.user)
        if o.state != 'draft': raise Conflict()
        p = o.current_production
        if request.data.get('production_id') != str(p.id): raise Conflict('生产稿已替换，请使用最新上传任务')
        if p.state in ('checking','ready'): return Response(order_data(o))
        if p.state != 'uploading': raise Conflict('请重新申请上传')
        storage.complete(p)
        p.state='checking'; p.error=''; p.save()
        o.file_state='checking'; event(o,'uploaded','生产文件已上传，正在校验',request.user)
        return Response(order_data(o))


class Payment(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        # 先持久化交易意图，网络超时后仍可用固定商户单号查单。
        with transaction.atomic():
            o = get_object_or_404(Order.objects.select_for_update(), pk=pk, owner=request.user)
            if 'pay' not in actions(o): raise Conflict('当前订单不可支付，请刷新')
            wechat.config()
            if not o.product.active: raise Conflict('该规格已暂停接单')
            if o.payment_expires_at and o.payment_expires_at <= timezone.now():
                raise Conflict('支付期限已过，请取消订单后重新下单')
            if not o.payment_expires_at: o.payment_expires_at=timezone.now()+timedelta(hours=2)
            o.payment_started=True; o.save()
        with transaction.atomic():
            o = Order.objects.select_for_update().get(pk=pk)
            if 'pay' not in actions(o): raise Conflict()
            if not o.prepay_id: o.prepay_id=wechat.create(o); o.save()
            return Response(wechat.app_parameters(o.prepay_id))


class RefreshPayment(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        get_object_or_404(Order, pk=pk, owner=request.user)
        return Response(order_data(reconcile(pk)))


class UserAction(APIView):
    permission_classes = [IsAuthenticated]
    @transaction.atomic
    def post(self, request, pk):
        o = get_object_or_404(Order.objects.select_for_update(), pk=pk, owner=request.user)
        if duplicate(o, request.data): return Response(order_data(o))
        check_revision(o, request.data)
        a = request.data.get('action')
        if a not in actions(o): raise Conflict('当前状态不支持此操作')
        if a == 'cancel': cancel(o, request.user)
        elif a == 'receive': o.state='completed'; event(o,'received','已确认收货',request.user)
        elif a == 'after_sale':
            o.after_sale_message = note(request.data); o.after_sale_state = 'open'; o.after_sale_resolution = ''
            event(o,'after_sale',o.after_sale_message,request.user)
        else: raise ValidationError('不支持的操作')
        receipt(o, request.data)
        return Response(order_data(o))


def check_revision(o, d):
    if d.get('revision') != o.revision: raise Conflict()


def note(d):
    value=d.get('message','')
    if not isinstance(value,str) or not 1 <= len(value.strip()) <= 1000: raise ValidationError('请填写 1–1000 字说明')
    return value.strip()


def key(d):
    try: return uuid.UUID(str(d.get('key')))
    except ValueError: raise ValidationError('缺少有效幂等键')


def duplicate(o,d):
    r=Receipt.objects.filter(order=o,key=key(d)).first()
    if r and r.fingerprint != digest(d): raise Conflict('重复请求内容不同')
    return r is not None


def receipt(o,d):
    Receipt.objects.create(order=o,key=key(d),fingerprint=digest(d))


class AdminOrders(APIView):
    permission_classes = [PrintAdmin]
    def get(self, request):
        all_orders = Order.objects.all()
        counts = dict(all_orders.values('state').annotate(n=Count('id')).values_list('state', 'n'))
        counts['after_sale'] = all_orders.filter(after_sale_state__in=['open', 'processing']).count()
        exception = Q(state__in=['paused','needs_revision']) | Q(file_state='failed') | Q(refund_state='exception')
        counts['exception'] = all_orders.filter(exception).count()
        qs = all_orders.select_related('current_production')
        state = request.query_params.get('state')
        if state == 'after_sale': qs = qs.filter(after_sale_state__in=['open','processing'])
        elif state == 'exception': qs = qs.filter(exception)
        elif state: qs = qs.filter(state=state)
        search = request.query_params.get('search','')[:120]
        if search: qs = qs.filter(Q(title__icontains=search)|Q(id__icontains=search.replace('-','')))
        offset = min(int(request.query_params.get('offset','0')) if request.query_params.get('offset','0').isdigit() else 0, 100000)
        total = qs.count()
        return Response(dict(results=[order_data(o, True, request.user, summary=True) for o in qs[offset:offset+30]],
                             total=total, counts=counts, next_offset=offset+30 if total>offset+30 else None))


class AdminDetail(APIView):
    permission_classes = [PrintAdmin]
    def get(self, request, pk): return Response(order_data(get_object_or_404(Order,pk=pk),True,request.user))

    @transaction.atomic
    def post(self, request, pk):
        o = get_object_or_404(Order.objects.select_for_update(), pk=pk)
        if duplicate(o, request.data): return Response(order_data(o,True,request.user))
        check_revision(o, request.data)
        operate(o, request.data, request.user)
        receipt(o, request.data)
        if request.data.get('action') == 'refresh_refund': o = reconcile(o.pk)
        return Response(order_data(o,True,request.user))


class Downloads(APIView):
    permission_classes = [PrintAdmin]
    def post(self,request,pk):
        if not request.user.has_perm('print_orders.download_order'): raise ValidationError('没有生产文件下载权限')
        o=get_object_or_404(Order,pk=pk)
        if not can_download(o, request.user): raise Conflict('此订单不能下载生产资源')
        p=o.current_production
        Event.objects.create(order=o,actor=request.user,action='download',message='工作人员获取生产文件')
        return Response(dict(version=p.number,production_id=str(p.id),expires_at=(timezone.now()+timedelta(minutes=5)).isoformat(),files={role:storage.download(v['key']) for role,v in p.result['files'].items()}))


class AdminProducts(APIView):
    permission_classes = [PrintAdmin]
    def get(self,request): return Response([product_data(p) for p in Product.objects.all()])
    @transaction.atomic
    def post(self,request):
        class Input(serializers.ModelSerializer):
            class Meta:
                model=Product
                exclude=[]
                read_only_fields=['id','revision','proof_at','proof_by']
                extra_kwargs={'paper': {'allow_blank': True}, 'binding': {'allow_blank': True}}
        existing=request.data.get('id')
        p=get_object_or_404(Product.objects.select_for_update(),pk=existing) if existing else None
        if p and request.data.get('revision')!=p.revision: raise Conflict()
        s=Input(p,data=request.data); s.is_valid(raise_exception=True)
        d=s.validated_data
        if d.get('cover_mode','separate_front_back')!='separate_front_back': raise ValidationError('暂只支持独立封面封底')
        if not 1<=d.get('min_pages',2)<=d.get('max_pages',200)<=500: raise ValidationError('页数限制不合法')
        if not 1<=d.get('max_quantity',10)<=100: raise ValidationError('每单份数须为 1–100')
        if not 1<=d.get('width_mm',148)<=500 or not 1<=d.get('height_mm',210)<=500: raise ValidationError('成品尺寸不合法')
        if not isinstance(d.get('regions',[]),list) or not all(isinstance(v,str) and v.strip() for v in d.get('regions',[])): raise ValidationError('配送地区需为名称列表')
        regions = list(dict.fromkeys(x.strip() for x in d.get('regions', [])))
        d['regions'] = regions
        proof_fields = ('width_mm', 'height_mm', 'paper', 'binding', 'duplex', 'cover_mode')
        changed = p and any(k in d and d[k] != getattr(p,k) for k in proof_fields)
        if changed and p.proof_approved and d.get('proof_approved') and not request.data.get('reproof_confirmed'):
            raise ValidationError('尺寸、纸张或工艺已变化，请重新实物打样并确认')
        if d.get('proof_approved') and not d.get('proof_note', '').strip(): raise ValidationError('请填写实物打样记录（材料、工艺与检查结果）')
        if d.get('active') and (not d.get('proof_approved') or not d.get('terms','').strip() or not regions
            or not d.get('paper','').strip() or not d.get('binding','').strip() or not d.get('lead_time','').strip()
            or (not d.get('free_printing') and d.get('base_fen',0)+d.get('page_fen',0)*d.get('min_pages',2)<=0)):
            raise ValidationError('开放前请完成纸张、装订、打样、价格、配送、制作周期及售后说明')
        proof_changed = d.get('proof_approved') and (not p or not p.proof_approved or changed or d.get('proof_note') != p.proof_note)
        extra = dict(revision=p.revision+1 if p else 1)
        if proof_changed: extra.update(proof_at=timezone.now(), proof_by=request.user.get_username())
        elif not d.get('proof_approved'): extra.update(proof_at=None, proof_by='')
        return Response(product_data(s.save(**extra)))



class Notification(APIView):
    authentication_classes=[]
    permission_classes=[]
    def post(self,request):
        try:
            data=wechat.notification(request.headers,request.body)
            with transaction.atomic():
                o=get_object_or_404(Order.objects.select_for_update(),pk=uuid.UUID(data['out_trade_no']))
                from .services import apply_payment
                apply_payment(o,data)
            return HttpResponse(status=204)
        except (ValueError,KeyError,TypeError):
            return Response({'code':'FAIL','message':'Invalid notification'},status=400)


class WorkerPermission(BasePermission):
    def has_permission(self,request,view):
        token=getattr(settings,'PRINT_PROCESSOR_TOKEN','')
        return bool(token and secrets.compare_digest(request.headers.get('X-Print-Token',''),token))


class Processor(APIView):
    authentication_classes=[]
    permission_classes=[WorkerPermission]
    @transaction.atomic
    def post(self,request):
        d=request.data
        if d.get('action')=='claim':
            p=Production.objects.select_for_update(skip_locked=True).filter(state='checking', order__state='draft').filter(Q(lease_until__isnull=True)|Q(lease_until__lt=timezone.now())).order_by('confirmed_at').first()
            if not p:return Response(status=204)
            if p.attempts>=5:
                p.state='failed'; p.error='文件处理多次中断，请联系工作人员'; p.save()
                o=Order.objects.select_for_update().get(pk=p.order_id); o.file_state='failed'; event(o,'check_failed',p.error)
                return Response(status=204)
            p.lease=uuid.uuid4(); p.lease_until=timezone.now()+timedelta(minutes=30); p.attempts+=1; p.save()
            return Response(dict(id=str(p.id),lease=str(p.lease),files=[dict(**f,key=storage.staging(p,f['role'])) for f in p.manifest],
                spec=p.order.spec,snapshot=p.order.snapshot,quantity=p.order.quantity,number=p.order.id.hex,
                output_prefix=f'{storage.prefix()}production/{p.id}/{p.lease}/'))
        p=get_object_or_404(Production.objects.select_for_update(),pk=d.get('id'))
        if str(p.lease)!=d.get('lease') or not p.lease_until or p.lease_until<timezone.now():raise Conflict('处理租约已过期')
        if p.state in ('ready','failed'): return Response({'state':p.state})
        o=Order.objects.select_for_update().get(pk=p.order_id)
        if o.state!='draft': raise Conflict('订单已取消或不可更新')
        if d.get('error'):
            p.state='failed'; p.error=str(d['error'])[:1000]; o.file_state='failed'
        else:
            result=d.get('result',{}); output=f'{storage.prefix()}production/{p.id}/{p.lease}/'
            files=result.get('files',{})
            if set(files)!={'interior','cover','manifest','production','archive'}:raise ValidationError('生产文件不完整')
            for role,f in files.items():
                if not isinstance(f,dict) or not str(f.get('key','')).startswith(output):raise ValidationError('生产路径非法')
                if role in ('interior','cover') and f.get('sha256')!=next(x['sha256'] for x in p.manifest if x['role']==role):raise ValidationError('用户确认的生产稿发生变化')
            p.result=result;p.state='ready';o.file_state='ready'
            if o.payment_state in ('paid','not_required'): o.state='awaiting_review'
        p.save(); event(o,'checked',('生产稿已就绪，等待印前审核' if o.payment_state in ('paid','not_required') else '生产文件已就绪，请支付') if p.state=='ready' else p.error)
        return Response({'state':p.state})
