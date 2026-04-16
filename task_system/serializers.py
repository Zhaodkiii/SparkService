from django.contrib.auth.models import User
from rest_framework import serializers

from medical.models import Member
from task_system.models import (
    Task,
    TaskDiet,
    TaskExecution,
    TaskExercise,
    TaskMedical,
    TaskNotification,
    TaskPlan,
    TaskStatus,
    TaskType,
)


class TaskMedicalSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskMedical
        fields = (
            "id",
            "task",
            "status",
            "reminder_time",
            "medical_task_type",
            "description",
            "source",
            "created_by",
            "operator",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "task", "created_by", "operator", "created_at", "updated_at")


class TaskExerciseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskExercise
        fields = (
            "id",
            "task",
            "status",
            "exercise_type",
            "duration_min",
            "intensity",
            "description",
            "source",
            "created_by",
            "operator",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "task", "created_by", "operator", "created_at", "updated_at")


class TaskDietSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskDiet
        fields = (
            "id",
            "task",
            "status",
            "meal_type",
            "calorie_target",
            "food_recommend",
            "description",
            "source",
            "created_by",
            "operator",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "task", "created_by", "operator", "created_at", "updated_at")


class TaskExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskExecution
        fields = (
            "id",
            "task",
            "user",
            "member",
            "business_type",
            "business_id",
            "related_sub_type",
            "related_sub_id",
            "status",
            "executed_at",
            "value",
            "notes",
            "created_at",
        )
        read_only_fields = ("id", "user", "created_at")


class TaskNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskNotification
        fields = (
            "id",
            "task",
            "member",
            "channel",
            "status",
            "template_code",
            "template_params",
            "reminder_time",
            "sent_at",
            "failed_reason",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class TaskSerializer(serializers.ModelSerializer):
    task_medical = TaskMedicalSerializer(required=False)
    task_exercise = TaskExerciseSerializer(required=False)
    task_diet = TaskDietSerializer(required=False)

    class Meta:
        model = Task
        fields = (
            "id",
            "member",
            "creator",
            "title",
            "description",
            "type",
            "status",
            "start_time",
            "due_time",
            "repeat_type",
            "priority",
            "business_type",
            "business_id",
            "source",
            "notification_id",
            "extra",
            "created_at",
            "updated_at",
            "task_medical",
            "task_exercise",
            "task_diet",
        )
        read_only_fields = ("id", "creator", "source", "created_at", "updated_at")

    def validate_member(self, value: Member):
        request = self.context.get("request")
        if request and value.user_id != request.user.id:
            raise serializers.ValidationError("member does not belong to current user")
        return value

    def validate(self, attrs):
        task_type = attrs.get("type", getattr(self.instance, "type", None))
        med = attrs.get("task_medical")
        ex = attrs.get("task_exercise")
        diet = attrs.get("task_diet")

        if task_type == TaskType.MEDICAL and not (med or getattr(self.instance, "task_medical", None)):
            raise serializers.ValidationError({"task_medical": "medical task extension is required"})
        if task_type == TaskType.EXERCISE and not (ex or getattr(self.instance, "task_exercise", None)):
            raise serializers.ValidationError({"task_exercise": "exercise task extension is required"})
        if task_type == TaskType.DIET and not (diet or getattr(self.instance, "task_diet", None)):
            raise serializers.ValidationError({"task_diet": "diet task extension is required"})
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        med_payload = validated_data.pop("task_medical", None)
        exercise_payload = validated_data.pop("task_exercise", None)
        diet_payload = validated_data.pop("task_diet", None)

        task = Task.objects.create(creator=request.user, **validated_data)
        self._upsert_sub_task(task, request.user, med_payload, exercise_payload, diet_payload)
        return task

    def update(self, instance: Task, validated_data):
        request = self.context["request"]
        med_payload = validated_data.pop("task_medical", None)
        exercise_payload = validated_data.pop("task_exercise", None)
        diet_payload = validated_data.pop("task_diet", None)

        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        self._upsert_sub_task(instance, request.user, med_payload, exercise_payload, diet_payload)
        return instance

    @staticmethod
    def _upsert_sub_task(task: Task, user: User, med_payload, exercise_payload, diet_payload):
        # 关键逻辑：主任务和子任务分别持久化，保证未来可按类型独立扩展字段。
        if task.type == TaskType.MEDICAL and med_payload:
            TaskMedical.objects.update_or_create(
                task=task,
                defaults={
                    **med_payload,
                    "created_by": user,
                    "operator": user,
                },
            )
        if task.type == TaskType.EXERCISE and exercise_payload:
            TaskExercise.objects.update_or_create(
                task=task,
                defaults={
                    **exercise_payload,
                    "created_by": user,
                    "operator": user,
                },
            )
        if task.type == TaskType.DIET and diet_payload:
            TaskDiet.objects.update_or_create(
                task=task,
                defaults={
                    **diet_payload,
                    "created_by": user,
                    "operator": user,
                },
            )


class TaskPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskPlan
        fields = (
            "id",
            "member",
            "creator",
            "title",
            "description",
            "status",
            "start_date",
            "end_date",
            "extra",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "creator", "created_at", "updated_at")


class TaskStatusSyncSerializer(serializers.ModelSerializer):
    task_id = serializers.IntegerField(source="id")

    class Meta:
        model = Task
        fields = ("task_id", "status", "updated_at")
