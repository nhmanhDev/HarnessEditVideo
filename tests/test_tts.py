import httpx
import pytest

from edit_agent.tts import TTSError, VoiceStudioTTS

AUDIO = b"RIFF-fake-wav-bytes"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")


def test_voicestudio_resolves_voice_by_name_then_polls_job(tmp_path):
    calls = []
    polls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if req.url.path == "/api/voices":
            return httpx.Response(200, json=[{"id": "v-1", "name": "Hoa"}, {"id": "v-2", "name": "Nam"}])
        if req.url.path == "/api/synthesize":
            body = req.read().decode()
            assert '"voiceId": "v-2"' in body or '"voiceId":"v-2"' in body
            assert '"async": true' in body or '"async":true' in body
            return httpx.Response(200, json={"success": True, "jobId": "j1"})
        if req.url.path == "/api/synthesize/job/j1":
            polls["n"] += 1
            if polls["n"] < 2:
                return httpx.Response(200, json={"success": True, "status": "running"})
            return httpx.Response(200, json={"success": True, "status": "done", "audioUrl": "/outputs/a.wav"})
        if req.url.path == "/outputs/a.wav":
            return httpx.Response(200, content=AUDIO)
        return httpx.Response(404)

    tts = VoiceStudioTTS(base_url="http://test", voice="nam", client=_client(handler), sleep=lambda _s: None)
    out = tmp_path / "voice" / "v0.wav"
    tts.synthesize("Xin chào", out)
    assert out.read_bytes() == AUDIO
    assert polls["n"] == 2


def test_voicestudio_reports_missing_license_clearly(tmp_path):
    def handler(req):
        if req.url.path == "/api/voices":
            return httpx.Response(200, json=[{"id": "v-1", "name": "Hoa"}])
        return httpx.Response(402, json={"success": False})

    tts = VoiceStudioTTS(base_url="http://test", voice="Hoa", client=_client(handler), sleep=lambda _s: None)
    with pytest.raises(TTSError, match="bản quyền"):
        tts.synthesize("x", tmp_path / "v.wav")


def test_voicestudio_lists_available_voices_when_name_unknown(tmp_path):
    def handler(req):
        return httpx.Response(200, json=[{"id": "v-1", "name": "Hoa"}])

    tts = VoiceStudioTTS(
        base_url="http://test", voice="ai-do", client=_client(handler), sleep=lambda _s: None
    )
    with pytest.raises(TTSError, match="Hoa"):
        tts.synthesize("x", tmp_path / "v.wav")


def test_voicestudio_job_error_is_surfaced(tmp_path):
    def handler(req):
        if req.url.path == "/api/voices":
            return httpx.Response(200, json=[{"id": "v-1", "name": "Hoa"}])
        if req.url.path == "/api/synthesize":
            return httpx.Response(200, json={"success": True, "jobId": "j9"})
        return httpx.Response(200, json={"success": True, "status": "error", "error": "hỏng"})

    tts = VoiceStudioTTS(base_url="http://test", voice="Hoa", client=_client(handler), sleep=lambda _s: None)
    with pytest.raises(TTSError, match="hỏng"):
        tts.synthesize("x", tmp_path / "v.wav")
