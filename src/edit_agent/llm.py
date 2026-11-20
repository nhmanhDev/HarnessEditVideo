"""Backend model thay được. Harness chỉ cần một hàm: đưa chữ và ảnh vào, nhận chữ ra.

- claude-cli: gọi Claude Code ở chế độ không giao diện (dùng quota Claude Code, không cần API key).
- anthropic: gọi Claude API qua SDK (cần ANTHROPIC_API_KEY).
- command: lệnh ngoài bất kỳ đọc prompt từ stdin và in câu trả lời ra stdout (Codex, Gemini...).

Mọi backend nhận danh sách ảnh theo đường dẫn tương đối so với thư mục làm việc (cwd).
"""

from __future__ import annotations

import base64
import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Protocol


class LLMError(RuntimeError):
    pass


class Backend(Protocol):
    name: str

    def complete(self, prompt: str, images: list[str], cwd: Path) -> str: ...


def _images_note(images: list[str]) -> str:
    if not images:
        return ""
    lines = "\n".join(f"- {p}" for p in images)
    return f"\n\nẢnh cần xem (đọc bằng công cụ Read, đường dẫn tương đối so với thư mục làm việc):\n{lines}\n"


class ClaudeCliBackend:
    """Gọi `claude -p` (Claude Code không giao diện). Model đọc ảnh bằng công cụ Read."""

    name = "claude-cli"

    def __init__(self, binary: str, model: str | None = None, timeout: int = 900, max_turns: int = 8) -> None:
        self._bin = binary
        self._model = model
        self._timeout = timeout
        self._max_turns = max_turns

    def complete(self, prompt: str, images: list[str], cwd: Path) -> str:
        cmd = [
            self._bin,
            "-p",
            "--allowedTools",
            "Read",
            "--output-format",
            "json",
            "--max-turns",
            str(self._max_turns),
        ]
        if self._model:
            cmd += ["--model", self._model]
        # Prompt đi qua stdin để không vướng giới hạn độ dài dòng lệnh trên Windows.
        proc = subprocess.run(
            cmd,
            input=prompt + _images_note(images),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self._timeout,
        )
        if proc.returncode != 0:
            raise LLMError(f"claude lỗi (mã {proc.returncode}): {proc.stderr.strip()[-300:]}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise LLMError(f"claude trả về không phải JSON: {proc.stdout[:200]}") from exc
        if data.get("is_error"):
            raise LLMError(f"claude báo lỗi: {str(data.get('result'))[:300]}")
        return str(data.get("result", ""))


class AnthropicBackend:
    """Gọi Claude API qua SDK. Ảnh gửi dạng base64."""

    name = "anthropic"

    def __init__(self, client, model: str, max_tokens: int = 4000) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, prompt: str, images: list[str], cwd: Path) -> str:
        content: list[dict] = []
        for rel in images:
            data = base64.b64encode((cwd / rel).read_bytes()).decode("ascii")
            content.append({"type": "text", "text": f"Ảnh {rel}:"})
            content.append(
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}
            )
        content.append({"type": "text", "text": prompt})
        resp = self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens, messages=[{"role": "user", "content": content}]
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


class CommandBackend:
    """Lệnh ngoài đọc prompt từ stdin, in câu trả lời ra stdout. Ảnh được nhắc theo đường dẫn trong prompt."""

    name = "command"

    def __init__(self, command: str, timeout: int = 900) -> None:
        self._cmd = shlex.split(command, posix=False)
        self._timeout = timeout

    def complete(self, prompt: str, images: list[str], cwd: Path) -> str:
        proc = subprocess.run(
            self._cmd,
            input=prompt + _images_note(images),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self._timeout,
        )
        if proc.returncode != 0:
            raise LLMError(f"lệnh lỗi (mã {proc.returncode}): {proc.stderr.strip()[-300:]}")
        return proc.stdout


def make_backend(
    name: str,
    *,
    claude_bin: str | None,
    claude_model: str | None,
    command: str | None,
    anthropic_client=None,
    anthropic_model: str = "claude-sonnet-5-5",
) -> Backend:
    if name == "claude-cli":
        binary = claude_bin or shutil.which("claude")
        if not binary:
            raise LLMError("Không thấy claude. Đặt CLAUDE_BIN trong .env trỏ tới claude.exe.")
        return ClaudeCliBackend(binary, claude_model)
    if name == "anthropic":
        if anthropic_client is None:
            raise LLMError("Backend anthropic cần ANTHROPIC_API_KEY.")
        return AnthropicBackend(anthropic_client, anthropic_model)
    if name == "command":
        if not command:
            raise LLMError("Backend command cần PLANNER_CMD, ví dụ: codex exec -")
        return CommandBackend(command)
    raise LLMError(f"Backend không hỗ trợ: {name}")
