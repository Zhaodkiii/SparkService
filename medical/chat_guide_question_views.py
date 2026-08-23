"""对话引导卡片科普问题登记与点击统计接口（BACKOFFICE-CONVERSATION-000001）。

客户端后台异步 best-effort 上报，失败或重复不影响主链路，因此接口保持轻量：
- register：AI 成功生成后登记问题；固定兜底 / 未绑定成员 / 生成失败场景不入表。
- click：用户点击已登记 AI 生成问题后，原子递增 click_count；找不到记录时返回可忽略结果。
"""

import logging

from django.db.models import F
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.response import error_response, success_response
from medical.models import ChatGuideGeneratedQuestionRecord, Member
from medical.services.member_permission_gate import MemberPermissionGate
from medical.chat_guide_question_serializers import (
    ChatGuideQuestionClickSerializer,
    ChatGuideQuestionRegisterSerializer,
)

logger = logging.getLogger("medical.chat_guide_question")


class ChatGuideQuestionRegisterAPI(APIView):
    """登记客户端 AI 成功生成的引导卡片科普问题。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatGuideQuestionRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member_id = serializer.validated_data["member_id"]
        questions = serializer.validated_data["questions"]

        try:
            MemberPermissionGate.require_access(user=request.user, member_id=member_id)
        except PermissionError:
            logger.info(
                "chat.guide.question.register_failed user=%s member=%s error=permission_denied",
                request.user.id,
                member_id,
            )
            return error_response(msg="permission_denied", code=-1, status_code=status.HTTP_403_FORBIDDEN)
        except Member.DoesNotExist:
            return error_response(msg="member_not_found", code=-1, status_code=status.HTTP_404_NOT_FOUND)

        items = []
        failures = []
        for question in questions:
            record = ChatGuideGeneratedQuestionRecord.objects.create(
                user=request.user,
                member_id=member_id,
                title=question["title"],
                prompt=question["prompt"],
                category=question.get("category") or "popular_science",
            )
            items.append(
                {
                    "client_question_id": question.get("id") or "",
                    "server_question_id": record.id,
                }
            )

        logger.info(
            "chat.guide.question.registered user=%s member=%s count=%s",
            request.user.id,
            member_id,
            len(items),
        )
        return success_response(
            {
                "registered": len(items),
                "failed": len(failures),
                "items": items,
                "failures": failures,
            },
            msg="success",
            code=0,
            status_code=status.HTTP_201_CREATED,
        )


class ChatGuideQuestionClickAPI(APIView):
    """上送点击统计：对已登记 AI 生成问题的 click_count 原子 +1。"""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatGuideQuestionClickSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        server_question_id = serializer.validated_data["server_question_id"]

        # 仅对当前用户自己的登记记录 +1，避免越权修改他人数据。
        updated = ChatGuideGeneratedQuestionRecord.objects.filter(
            id=server_question_id,
            user=request.user,
        ).update(click_count=F("click_count") + 1)

        if not updated:
            logger.info(
                "chat.guide.question.clicked.user_missing user=%s question=%s",
                request.user.id,
                server_question_id,
            )
            return success_response(
                {
                    "accepted": False,
                    "server_question_id": server_question_id,
                    "click_count": None,
                },
                msg="ignored",
                code=0,
                status_code=status.HTTP_200_OK,
            )

        record = ChatGuideGeneratedQuestionRecord.objects.get(id=server_question_id)
        logger.info(
            "chat.guide.question.clicked user=%s member=%s question=%s",
            request.user.id,
            record.member_id,
            server_question_id,
        )
        return success_response(
            {
                "accepted": True,
                "server_question_id": server_question_id,
                "click_count": record.click_count,
            },
            msg="success",
            code=0,
            status_code=status.HTTP_200_OK,
        )