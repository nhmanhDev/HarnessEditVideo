import json
from types import SimpleNamespace

from edit_agent.planner import extract_json_object, plan_edit
from edit_agent.spec import JobSpec, JobType

VALID = {
    "segments": [{"src_start": 0, "src_end": 4}],
    "texts": [{"text": "Mở đầu", "start": 0, "end": 2, "position": "top"}],
    "voice_lines": [],
    "music": {"track": None, "volume": 0.2},
    "notes": "ngắn gọn",
}


class FakeClient:
    """Trả về lần lượt các câu trả lời đã cho, đúng như API Claude sẽ trả."""

    def __init__(self, *texts):
        self._texts = list(texts)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self._texts.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def test_extract_json_handles_code_fence_and_prose():
    text = "Đây là kế hoạch:\n```json\n" + json.dumps(VALID) + "\n```"
    assert extract_json_object(text)["notes"] == "ngắn gọn"


def test_plan_edit_retries_once_after_invalid_plan(tmp_path):
    bad = json.dumps({"segments": []})
    client = FakeClient(bad, json.dumps(VALID))
    spec = JobSpec(input="x.mp4", job_type=JobType.TEXT_MUSIC)
    plan = plan_edit(client, "claude-sonnet-5-5", spec, 10.0, [], [], [], [])
    assert plan.segments[0].src_end == 4
    assert len(client.calls) == 2
    # Lần gọi thứ hai phải mang theo thông báo lỗi để model sửa.
    assert "không hợp lệ" in client.calls[1]["messages"][-1]["content"]


def test_plan_edit_gives_up_after_two_invalid_answers():
    import pytest

    from edit_agent.planner import PlannerError

    client = FakeClient("không phải json", "vẫn không")
    spec = JobSpec(input="x.mp4", job_type=JobType.TEXT_MUSIC)
    with pytest.raises(PlannerError):
        plan_edit(client, "claude-sonnet-5-5", spec, 10.0, [], [], [], [])
