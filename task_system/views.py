import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import error_response, success_response
from medical.models import Member
from task_system.notification_tasks import dispatch_task_notification_task
from task_system.models import (
    Task,
    TaskDiet,
    TaskExecution,
    TaskExecutionStatus,
    TaskExercise,
    TaskMedical,
    TaskNotification,
    TaskNotificationStatus,
    TaskRepeatType,
    TaskStatus,
    TaskSubRelatedType,
    TaskType,
)
from task_system.serializers import (
    TaskExecutionSerializer,
    TaskNotificationSerializer,
    TaskSerializer,
    TaskStatusSyncSerializer,
)

logger = logging.getLogger("task.system")


class _TaskBaseAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _parse_since(since_raw: str):
        if not since_raw:
            return None
        parsed = parse_datetime(since_raw)
        if parsed is None:
            return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def _member_or_404(self, member_id: int):
        member = Member.objects.filter(id=member_id, user_id=self.request.user.id, is_deleted=False).first()
        if member is None:
            return None
        return member

    def _task_or_404(self, task_id: int):
        return Task.objects.filter(id=task_id, member__user_id=self.request.user.id).first()


class TaskListCreateAPI(_TaskBaseAPIView):
    """POST /tasks/ 与 GET /tasks/。"""

    def get(self, request):
        member_id = request.query_params.get("member_id")
        since = self._parse_since(request.query_params.get("since", ""))

        queryset = (
            Task.objects.select_related("member", "creator")
            .prefetch_related("task_medical", "task_exercise", "task_diet")
            .filter(member__user_id=request.user.id)
        )
        if member_id:
            queryset = queryset.filter(member_id=member_id)
        if since:
            queryset = queryset.filter(updated_at__gt=since)
        serializer = TaskSerializer(queryset.order_by("-updated_at"), many=True)
        return success_response(serializer.data)

    def post(self, request):
        serializer = TaskSerializer(data=request.data, context={"request": request})
        if serializer.is_valid() is False:
            return error_response(msg="invalid_params", data=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            task = serializer.save()
            self._create_default_notification_if_needed(task)

        logger.info("task created id=%s member=%s by=%s", task.id, task.member_id, request.user.id)
        output = TaskSerializer(task).data
        return success_response(output, msg="created", status_code=status.HTTP_201_CREATED)

    def _create_default_notification_if_needed(self, task: Task):
        # 关键逻辑：创建后预置提醒策略，统一给 iOS 本地通知与服务端调度同步使用。
        reminder_time = task.start_time or task.due_time
        if task.type == TaskType.MEDICAL and hasattr(task, "task_medical") and task.task_medical.reminder_time:
            reminder_time = task.task_medical.reminder_time
        if reminder_time is None:
            return

        params = {
            "title": "健康任务提醒",
            "content": f"你有一个待完成任务：{task.title}",
            "task_id": task.id,
            "repeat_type": task.repeat_type,
        }
        notification = TaskNotification.objects.create(
            task=task,
            member=task.member,
            status=TaskNotificationStatus.PENDING,
            reminder_time=reminder_time,
            template_params=params,
            template_code="health_task_default",
        )

        # 可选 Celery：如果设置了提醒时间，则由服务端异步调度一次提醒。
        if reminder_time > timezone.now() - timedelta(seconds=5):
            dispatch_task_notification_task.apply_async(args=[notification.id], eta=reminder_time)


class TaskDetailAPI(_TaskBaseAPIView):
    """PATCH /tasks/{id}/。"""

    def patch(self, request, task_id: int):
        task = self._task_or_404(task_id)
        if task is None:
            return error_response(msg="task_not_found", status_code=status.HTTP_404_NOT_FOUND)

        serializer = TaskSerializer(task, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid() is False:
            return error_response(msg="invalid_params", data=serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        task = serializer.save()
        logger.info("task updated id=%s by=%s", task.id, request.user.id)
        return success_response(TaskSerializer(task).data, msg="updated")


class TaskCompleteAPI(_TaskBaseAPIView):
    """POST /tasks/{id}/complete。"""

    def post(self, request, task_id: int):
        task = self._task_or_404(task_id)
        if task is None:
            return error_response(msg="task_not_found", status_code=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            executed_at = request.data.get("executed_at")
            if isinstance(executed_at, str) and executed_at:
                parsed_executed_at = parse_datetime(executed_at)
                if parsed_executed_at is not None:
                    if timezone.is_naive(parsed_executed_at):
                        parsed_executed_at = timezone.make_aware(parsed_executed_at, timezone.get_current_timezone())
                    executed_at = parsed_executed_at
            if not executed_at:
                executed_at = timezone.now()

            task.status = TaskStatus.COMPLETED
            task.save(update_fields=["status", "updated_at"])
            _sync_sub_task_status(task, TaskStatus.COMPLETED, request.user.id)

            TaskExecution.objects.create(
                task=task,
                user=request.user,
                member=task.member,
                business_type=request.data.get("business_type", task.business_type),
                business_id=request.data.get("business_id", task.business_id),
                related_sub_type=self._related_sub_type(task.type),
                related_sub_id=self._related_sub_id(task),
                status=TaskExecutionStatus.DONE,
                executed_at=executed_at,
                value=request.data.get("value") or {},
                notes=request.data.get("notes", ""),
            )

            TaskNotification.objects.filter(task=task, status=TaskNotificationStatus.PENDING).update(
                status=TaskNotificationStatus.SENT,
                sent_at=timezone.now(),
                updated_at=timezone.now(),
            )

        logger.info("task completed id=%s by=%s", task.id, request.user.id)
        return success_response({"task_id": task.id, "status": task.status, "updated_at": task.updated_at}, msg="completed")

    @staticmethod
    def _related_sub_type(task_type: int) -> str:
        if task_type == TaskType.MEDICAL:
            return TaskSubRelatedType.MEDICAL
        if task_type == TaskType.EXERCISE:
            return TaskSubRelatedType.EXERCISE
        if task_type == TaskType.DIET:
            return TaskSubRelatedType.DIET
        return ""

    @staticmethod
    def _related_sub_id(task: Task):
        if task.type == TaskType.MEDICAL and hasattr(task, "task_medical"):
            return task.task_medical.id
        if task.type == TaskType.EXERCISE and hasattr(task, "task_exercise"):
            return task.task_exercise.id
        if task.type == TaskType.DIET and hasattr(task, "task_diet"):
            return task.task_diet.id
        return None


class TaskCancelAPI(_TaskBaseAPIView):
    """POST /tasks/{id}/cancel。"""

    def post(self, request, task_id: int):
        task = self._task_or_404(task_id)
        if task is None:
            return error_response(msg="task_not_found", status_code=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            task.status = TaskStatus.CANCELED
            task.save(update_fields=["status", "updated_at"])
            _sync_sub_task_status(task, TaskStatus.CANCELED, request.user.id)
            TaskNotification.objects.filter(task=task, status=TaskNotificationStatus.PENDING).update(
                status=TaskNotificationStatus.FAILED,
                failed_reason="task_canceled",
                updated_at=timezone.now(),
            )

        logger.info("task canceled id=%s by=%s", task.id, request.user.id)
        return success_response({"task_id": task.id, "status": task.status, "updated_at": task.updated_at}, msg="canceled")


class TaskExecutionListAPI(_TaskBaseAPIView):
    """GET /tasks/{id}/executions。"""

    def get(self, request, task_id: int):
        task = self._task_or_404(task_id)
        if task is None:
            return error_response(msg="task_not_found", status_code=status.HTTP_404_NOT_FOUND)

        queryset = TaskExecution.objects.filter(task_id=task.id).order_by("-executed_at")
        return success_response(TaskExecutionSerializer(queryset, many=True).data)


class TaskNotificationListAPI(_TaskBaseAPIView):
    """GET /tasks/{id}/notifications。"""

    def get(self, request, task_id: int):
        task = self._task_or_404(task_id)
        if task is None:
            return error_response(msg="task_not_found", status_code=status.HTTP_404_NOT_FOUND)

        queryset = TaskNotification.objects.filter(task_id=task.id).order_by("-reminder_time")
        return success_response(TaskNotificationSerializer(queryset, many=True).data)


class TaskSyncAPI(_TaskBaseAPIView):
    """GET /tasks/sync/?since=... 增量同步。"""

    def get(self, request):
        since = self._parse_since(request.query_params.get("since", ""))
        member_id = request.query_params.get("member_id")

        tasks = Task.objects.filter(member__user_id=request.user.id)
        if member_id:
            tasks = tasks.filter(member_id=member_id)

        if since:
            tasks = tasks.filter(updated_at__gt=since)

        task_data = TaskSerializer(tasks.order_by("-updated_at"), many=True).data
        status_data = TaskStatusSyncSerializer(tasks, many=True).data

        payload = {
            "tasks": task_data,
            "task_statuses": status_data,
            "server_time": timezone.now(),
        }
        return success_response(payload)


class TaskQueryByMemberAPI(_TaskBaseAPIView):
    """AI 预查询接口（任务生成前必须调用）。"""

    def get(self, request):
        member_id = request.query_params.get("member_id")
        if not member_id:
            return error_response(msg="member_id_required", status_code=status.HTTP_400_BAD_REQUEST)

        member = self._member_or_404(int(member_id))
        if member is None:
            return error_response(msg="member_not_found", status_code=status.HTTP_404_NOT_FOUND)

        tasks = (
            Task.objects.filter(member_id=member.id)
            .select_related("member")
            .prefetch_related("task_medical", "task_exercise", "task_diet", "executions")
            .order_by("-updated_at")
        )

        payload = []
        for task in tasks:
            item = TaskSerializer(task).data
            item["executions"] = TaskExecutionSerializer(task.executions.all().order_by("-executed_at")[:20], many=True).data
            payload.append(item)

        return success_response({"member_id": member.id, "tasks": payload})


class AITaskCandidateAnalyzeAPI(_TaskBaseAPIView):
    """任务相似性分析（给 Tool Calling 前置判断使用）。"""

    def post(self, request):
        member_id = request.data.get("member_id")
        if not member_id:
            return error_response(msg="member_id_required", status_code=status.HTTP_400_BAD_REQUEST)

        member = self._member_or_404(int(member_id))
        if member is None:
            return error_response(msg="member_not_found", status_code=status.HTTP_404_NOT_FOUND)

        task_type = request.data.get("task_type")
        target = (request.data.get("target_metric") or "").strip()

        queryset = Task.objects.filter(member_id=member.id)
        if task_type is not None:
            queryset = queryset.filter(type=task_type)

        similar = queryset.filter(
            Q(title__icontains=target)
            | Q(description__icontains=target)
            | Q(task_medical__description__icontains=target)
            | Q(task_exercise__description__icontains=target)
            | Q(task_diet__description__icontains=target)
        ).distinct()[:10]

        result = {
            "has_similar": similar.exists(),
            "similar_task_ids": [item.id for item in similar],
            "reason": "matched_by_metric" if similar.exists() else "no_similar_task",
        }
        return success_response(result)


def _sync_sub_task_status(task: Task, status_value: int, operator_id: int):
    # 状态镜像：保证总表与子表状态一致，避免客户端拉取后出现冲突。
    if task.type == TaskType.MEDICAL and hasattr(task, "task_medical"):
        TaskMedical.objects.filter(task_id=task.id).update(status=status_value, operator_id=operator_id, updated_at=timezone.now())
    if task.type == TaskType.EXERCISE and hasattr(task, "task_exercise"):
        TaskExercise.objects.filter(task_id=task.id).update(status=status_value, operator_id=operator_id, updated_at=timezone.now())
    if task.type == TaskType.DIET and hasattr(task, "task_diet"):
        TaskDiet.objects.filter(task_id=task.id).update(status=status_value, operator_id=operator_id, updated_at=timezone.now())
