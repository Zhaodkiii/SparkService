"""Shared workflow projection for the admin workspace and the owner client."""
from datetime import timedelta
from django.db.models import Exists, OuterRef, Q, Subquery, F
from django.utils import timezone
from .models import Submission, Event, Delivery

TERMINAL = ('completed', 'cancelled', 'rejected')
PRODUCTION = ('in_production', 'revision_requested', 'delivered')


def annotated_requests(qs):
    return qs.annotate(
        latest_submission_id=Subquery(Submission.objects.filter(request_id=OuterRef('pk')).order_by('-number').values('pk')[:1]),
        cancellation_requested=Exists(Event.objects.filter(request_id=OuterRef('pk'), action='cancellation_requested')),
        has_candidate=Exists(Delivery.objects.filter(request_id=OuterRef('pk'), status='ready_for_review', submission_id=OuterRef('accepted_submission_id'))),
    )


def pending_query():
    return Q(latest_submission_id__isnull=False, accepted_submission_id__isnull=True) | (
        Q(latest_submission_id__isnull=False, accepted_submission_id__isnull=False) & ~Q(latest_submission_id=F('accepted_submission_id')))


def facts(obj):
    latest = getattr(obj, 'latest_submission_id', None)
    if latest is None:
        latest = obj.submissions.order_by('-number').values_list('pk', flat=True).first()
    active = obj.status not in TERMINAL
    return dict(latest_submission_id=latest,
                pending_submission=active and latest is not None and latest != obj.accepted_submission_id,
                cancellation_requested=active and (obj.cancellation_requested if hasattr(obj,'cancellation_requested') else obj.events.filter(action='cancellation_requested').exists()),
                overdue=active and bool(obj.due_at and obj.due_at < timezone.now()))


def actions(obj, admin=False):
    f = facts(obj)
    result = []
    if admin:
        if obj.status in ('submitted', 'revision_requested') or (obj.status == 'in_production' and f['pending_submission']): result.append('accept')
        if obj.status in ('submitted', 'in_production'): result.append('request-info')
        if obj.status not in TERMINAL: result += ['production', 'assign', 'cancel', 'reject']
        if obj.status in PRODUCTION and obj.accepted_submission_id and not f['pending_submission']: result += ['upload', 'deliver']
        if obj.status in ('needs_info', 'delivered'): result.append('remind')
        if obj.status not in TERMINAL: result += ['withdraw', 'rollback']
    else:
        if obj.status in ('draft', 'needs_info'): result += ['edit', 'upload', 'submit']
        if obj.status in ('draft', 'submitted', 'needs_info'): result.append('cancel')
        if obj.status in ('in_production', 'revision_requested') and not f['cancellation_requested']: result.append('cancel')
        if obj.status == 'delivered': result += ['confirm', 'revision'] if obj.revision_round < 2 else ['confirm']
        result.append('delete')
    return result


def next_step(obj):
    f = facts(obj)
    if f['cancellation_requested']: return '用户申请取消，请先查看原因并处理'
    if obj.status == 'in_production' and f['pending_submission']: return '用户已补充资料，请查看新提交并确认制作依据'
    return {'draft':'用户尚未提交，等待完善资料', 'submitted':'查看提交资料，受理或要求补充',
            'needs_info':'等待用户补充资料', 'in_production':'下载制作资料，完成 PSD 后上传成品候选',
            'revision_requested':'查看修改意见，确认依据后开始修订', 'delivered':'等待用户查看与确认，可处理修改反馈',
            'completed':'用户已确认完成', 'cancelled':'需求已取消', 'rejected':'已告知用户暂无法制作'}.get(obj.status, '')


def reminder_available_at(obj):
    last = obj.events.filter(action='pending_reminder').order_by('-created_at').values_list('created_at', flat=True).first()
    return last + timedelta(hours=1) if last else None
