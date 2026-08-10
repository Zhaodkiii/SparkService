"""任务系统 Tool Calling 定义。

此文件给 AI 编排层使用：
1) 先调用任务查询工具 query_tasks_by_member；
2) 再基于抽取结果生成任务 JSON；
3) 如果命中相似任务，返回 "should_create": false。
"""

TASK_EXTRACTION_RULES = {
    "required_fields": [
        "task_type",  # medical/exercise/diet
        "target_metric",  # 血糖/体重/步数等
        "time_info",  # 开始时间/频率/周期
        "action",  # 测量/运动/饮食控制
        "intensity_or_value",  # 每天2次/8000步
    ],
    "task_type_mapping": {
        "medical": 0,
        "exercise": 1,
        "diet": 2,
    },
}

QUERY_TASKS_BY_MEMBER_TOOL = {
    "type": "function",
    "function": {
        "name": "query_tasks_by_member",
        "description": "查询 member 维度所有任务、子任务与执行状态（生成任务前必须先调用）",
        "parameters": {
            "type": "object",
            "properties": {
                "member_id": {
                    "type": "integer",
                    "description": "成员 ID",
                },
                "include_executions": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "required": ["member_id"],
            "additionalProperties": False,
        },
    },
}

GENERATE_TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_task_json",
        "description": "基于抽取结果与历史任务分析生成可直接创建任务的 JSON",
        "parameters": {
            "type": "object",
            "properties": {
                "member_id": {"type": "integer"},
                "creator_id": {"type": "integer"},
                "business_type": {"type": "string"},
                "business_id": {"type": "string"},
                "extracted": {
                    "type": "object",
                    "properties": {
                        "task_type": {"type": "string", "enum": ["medical", "exercise", "diet"]},
                        "target_metric": {"type": "string"},
                        "time_info": {"type": "string"},
                        "action": {"type": "string"},
                        "intensity_or_value": {"type": "string"},
                    },
                    "required": ["task_type", "target_metric", "time_info", "action", "intensity_or_value"],
                },
                "similarity_analysis": {
                    "type": "object",
                    "properties": {
                        "has_similar": {"type": "boolean"},
                        "similar_task_ids": {"type": "array", "items": {"type": "integer"}},
                        "reason": {"type": "string"},
                    },
                    "required": ["has_similar"],
                },
            },
            "required": ["member_id", "creator_id", "extracted", "similarity_analysis"],
            "additionalProperties": False,
        },
    },
}

TASK_OUTPUT_EXAMPLE = {
    "task": {
        "member_id": 1,
        "creator_id": 10,
        "title": "每日血糖监测",
        "description": "早晚各测一次血糖并记录",
        "type": 0,
        "status": 0,
        "repeat_type": 1,
        "priority": 0,
        "source": 1,
        "start_time": "2026-04-15T09:00:00Z",
        "due_time": "2026-04-30T09:00:00Z",
    },
    "task_medical": {
        "medical_task_type": "blood_glucose_monitoring",
        "reminder_time": "2026-04-15T09:00:00Z",
        "description": "每天两次监测空腹/餐后血糖",
    },
}

TASK_TOOL_CALLING_SYSTEM_PROMPT = """
你是医疗 AI 任务助手。生成任务前必须执行：
1) 调用 query_tasks_by_member(member_id)；
2) 使用抽取模块输出 task_type/target_metric/time_info/action/intensity_or_value；
3) 相似任务命中时，输出 should_create=false 且不创建任务；
4) 未命中时输出主任务 + 子任务 JSON，且只能输出 JSON，不带解释文本。
"""

TASK_GENERATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "should_create": {"type": "boolean"},
        "reason": {"type": "string"},
        "task": {"type": "object"},
        "task_medical": {"type": "object"},
        "task_exercise": {"type": "object"},
        "task_diet": {"type": "object"},
        "business_type": {"type": "string"},
        "business_id": {"type": "string"},
    },
    "required": ["should_create"],
    "additionalProperties": False,
}
