"""对话引导卡片科普问题登记 / 点击统计的客户端请求序列化器（BACKOFFICE-CONVERSATION-000001）。"""

from rest_framework import serializers


class ChatGuideQuestionRegisterItemSerializer(serializers.Serializer):
    """单条 AI 生成问题的登记项。

    ``id`` 为客户端问题标识，用于客户端把返回的 ``server_question_id`` 映射回本地问题；
    服务端不据此做幂等，第一阶段接受重复登记误差。
    """

    id = serializers.CharField(required=False, allow_blank=True, default="")
    title = serializers.CharField(max_length=120)
    prompt = serializers.CharField()
    category = serializers.CharField(required=False, allow_blank=True, default="popular_science")


class ChatGuideQuestionRegisterSerializer(serializers.Serializer):
    """批量登记 AI 生成科普问题。"""

    member_id = serializers.IntegerField(min_value=1)
    questions = ChatGuideQuestionRegisterItemSerializer(many=True, allow_empty=False)


class ChatGuideQuestionClickSerializer(serializers.Serializer):
    """点击统计上送。"""

    server_question_id = serializers.IntegerField(min_value=1)
    member_id = serializers.IntegerField(min_value=1, required=False)