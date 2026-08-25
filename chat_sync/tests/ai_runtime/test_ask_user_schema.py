from chat_sync.ai_runtime.tools.ask_user_schema import build_ask_user_payload


def test_ask_user_normalizes_legacy_shape_and_limits_options():
    payload, error = build_ask_user_payload(question="选择范围", options=["最近 7 天", "其他", "最近 30 天"])
    assert error is None
    assert payload.question_ids == ("q1",)
    assert [item.label for item in payload.questions[0].options] == ["最近 7 天", "最近 30 天"]


def test_ask_user_deduplicates_ids_and_truncates_question_count():
    payload, error = build_ask_user_payload(questions=[{"id": "q", "prompt": "a"}, {"id": "q", "prompt": "b"}] * 3)
    assert error is None
    assert len(payload.questions) == 4
    assert payload.question_ids == ("q", "q_2", "q_3", "q_4")

