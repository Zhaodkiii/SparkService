"""后台履约规则；按钮能力和写接口共享同一套规则。"""
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .domain import Conflict
from .models import Shipment
from .services import event, cancel

CHECKLISTS = {
    'approve': {'cover': '正封面和封底正确', 'pages': '内页页序及空白页正确', 'size': '尺寸、裁切和装订留白合适', 'quality': '图片与文字清晰'},
    'start': {'files': '已下载并核对当前生产稿', 'spec': '纸张、单双面、装订与份数已核对'},
    'finish': {'pages': '无漏页、错页或倒页', 'trim': '裁切与装订方向正确', 'appearance': '外观完整、印刷清晰', 'quantity': '成品份数正确'},
}


def capabilities(o, user):
    result = []
    funded = o.payment_state in ('paid', 'not_required') and not o.cancel_requested
    ready = funded and o.file_state == 'ready'
    if o.state in ('draft', 'awaiting_review', 'queued', 'needs_revision'): result.append('cancel')
    if ready:
        result += {'awaiting_review': ['approve', 'needs_revision'], 'queued': ['start', 'needs_revision', 'pause'],
                   'producing': ['finish', 'pause', 'reprint'], 'ready_to_ship': ['ship', 'pause', 'reprint'],
                   'paused': ['resume', 'reprint'], 'shipped': ['correct_shipment', 'reship', 'complete'],
                   'completed': ['correct_shipment', 'reship']}.get(o.state, [])
    if o.after_sale_state == 'open': result.append('accept_after_sale')
    if o.after_sale_state in ('open', 'processing'): result.append('resolve_after_sale')
    if user.has_perm('print_orders.refund_order'):
        if o.payment_state == 'paid' and o.state != 'producing': result.append('refund')
        if o.refund_state in ('pending', 'processing', 'exception'): result.append('refresh_refund')
    return result


def can_download(o, user):
    return (user.has_perm('print_orders.download_order') and o.file_state == 'ready'
            and o.payment_state in ('paid', 'not_required') and not o.cancel_requested
            and o.state not in ('cancelled', 'needs_revision', 'draft'))


def note(data):
    value = data.get('message', '')
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 1000:
        raise ValidationError('请填写 1–1000 字说明')
    return value.strip()


def operate(o, data, actor):
    a = data.get('action')
    if a not in capabilities(o, actor): raise Conflict('订单状态或权限已变化，请刷新后重试')
    details = {}
    if a in CHECKLISTS:
        checks = data.get('checklist', [])
        if not isinstance(checks, list) or not all(isinstance(x, str) for x in checks) or set(checks) != set(CHECKLISTS[a]):
            raise ValidationError('请逐项完成检查后再提交')
        if data.get('production_id') != str(o.current_production_id):
            raise Conflict('生产稿已变化，请重新预览并检查')
        details = {'checklist': list(CHECKLISTS[a].values()), 'production_number': o.current_production.number}
    if a == 'cancel':
        cancel(o, actor); return
    if a == 'refund':
        o.refund_reason = note(data)[:200]; o.refund_state = 'pending'; o.payment_state = 'refund_pending'; o.cancel_requested = True
        if o.state not in ('shipped', 'completed'): o.state = 'cancelled'
        message = '申请全额退款：' + o.refund_reason
    elif a == 'refresh_refund':
        # 异常交易先查原退款单，不创建另一笔退款。
        if o.refund_state == 'exception': o.refund_state = 'processing'
        message = '已请求核对原退款单，等待支付对账任务更新结果'
    elif a == 'approve': o.state = 'queued'; message = '印前审核通过，等待制作'
    elif a == 'needs_revision':
        o.state = 'needs_revision'; o.exception_reason = note(data)
        message = '请修改后在原作品的装订成册页面重新提交：' + o.exception_reason
    elif a == 'start': o.state = 'producing'; message = '开始打印装订'
    elif a == 'finish': o.state = 'ready_to_ship'; message = '制作及质检完成，等待发货'
    elif a == 'pause':
        o.paused_from = o.state; o.state = 'paused'; o.exception_reason = note(data); message = '暂停制作：' + o.exception_reason
    elif a == 'resume':
        reason = note(data)
        if o.paused_from not in ('queued', 'producing', 'ready_to_ship'): raise Conflict('没有可恢复的制作阶段')
        o.state = o.paused_from; o.paused_from = ''; o.exception_reason = ''; message = '恢复制作：' + reason
    elif a == 'reprint':
        o.state = 'queued'; o.paused_from = ''; o.exception_reason = ''; message = '安排重印，重新制作和质检：' + note(data)
    elif a in ('ship', 'reship', 'correct_shipment'):
        class ShippingInput(serializers.Serializer):
            carrier = serializers.CharField(max_length=80)
            tracking_number = serializers.RegexField(r'^[A-Za-z0-9-]{5,80}$')
        s = ShippingInput(data=data); s.is_valid(raise_exception=True)
        if data.get('address_confirmed') is not True: raise ValidationError('请核对收件人与地址')
        if a == 'correct_shipment':
            shipment_id = serializers.IntegerField(min_value=1).run_validation(data.get('shipment_id'))
            shipment = o.shipments.filter(pk=shipment_id).first()
            if not shipment: raise ValidationError('请选择需要更正的发货记录')
            details['before'] = {'carrier': shipment.carrier, 'tracking_number': shipment.tracking_number}
            shipment.carrier = s.validated_data['carrier']; shipment.tracking_number = s.validated_data['tracking_number']; shipment.save()
            message = '更正物流信息：' + note(data)
        else:
            shipment = Shipment.objects.create(order=o, kind='reship' if a == 'reship' else 'initial', **s.validated_data)
            o.state = 'shipped'; o.stage_started_at = timezone.now()
            message = '补寄已交寄：' + note(data) if a == 'reship' else '已交寄快递'
        details.update(shipment_id=shipment.id, **s.validated_data)
    elif a == 'complete':
        o.state = 'completed'; message = '工作人员核实收货并完成订单：' + note(data)
    elif a == 'accept_after_sale':
        o.after_sale_state = 'processing'; message = '售后处理中'
    elif a == 'resolve_after_sale':
        o.after_sale_resolution = note(data); o.after_sale_state = 'resolved'; message = '售后处理完成：' + o.after_sale_resolution
    event(o, a, message, actor, details)
