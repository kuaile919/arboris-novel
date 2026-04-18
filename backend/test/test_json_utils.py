import json

from app.utils.json_utils import sanitize_json_like_text, unwrap_markdown_json


def test_unwrap_markdown_json_preserves_outer_json_when_message_contains_code_fence():
    response = json.dumps(
        {
            "ai_message": (
                "从纨绔日常开篇\n\n"
                "```\\n"
                "第1章：纨绔日常\\n"
                "第2章：当头棒喝\\n"
                "```"
            ),
            "ui_control": {
                "type": "single_choice",
                "options": [{"id": "qidian", "label": "起点中文网"}],
                "placeholder": "",
            },
            "conversation_state": {"step": "platform_choice"},
            "is_complete": False,
        },
        ensure_ascii=False,
    )

    unwrapped = unwrap_markdown_json(response)
    parsed = json.loads(unwrapped)

    assert parsed["ui_control"]["type"] == "single_choice"
    assert "第1章：纨绔日常" in parsed["ai_message"]


def test_unwrap_markdown_json_extracts_fenced_json_block():
    response = """
这里是说明文字

```json
{"status":"ok","value":1}
```
"""

    assert unwrap_markdown_json(response) == '{"status":"ok","value":1}'


def test_unwrap_markdown_json_keeps_outer_json_like_payload_for_sanitizing():
    response = """
{
  "ai_message": "第一行
第二行",
  "ui_control": {
    "type": "single_choice",
    "options": [{"id": "a", "label": "A"}],
    "placeholder": ""
  },
  "conversation_state": {},
  "is_complete": false
}
"""

    unwrapped = unwrap_markdown_json(response)
    parsed = json.loads(sanitize_json_like_text(unwrapped))

    assert parsed["ui_control"]["type"] == "single_choice"
    assert parsed["conversation_state"] == {}
