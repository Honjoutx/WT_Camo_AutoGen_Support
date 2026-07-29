from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Dict, Optional

from . import state
from .qt import QtCore


ASSET_MARKER = re.compile(
    r"(?:LIVERY_ASSET|涂装素材)\s*:\s*[`\"']?([^`\"'\r\n]+)",
    re.IGNORECASE,
)


def find_asset_marker(message: str) -> str:
    match = ASSET_MARKER.search(message or "")
    return match.group(1).strip() if match else ""


def _json_request(url: str, *, payload=None, timeout=8):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            details = json.loads(raw)
            message = str(details.get("error") or raw).strip()
        except Exception:
            message = ""
        if message:
            raise RuntimeError(message) from exc
        raise RuntimeError(f"Agent 服务返回 HTTP {exc.code}") from exc


def _python_for_server(root: Path) -> str:
    candidates = [
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("python") or sys.executable


class AgentController(QtCore.QObject):
    event = QtCore.Signal(object)

    def __init__(self, project_root: Path, base_url: str, parent=None):
        super().__init__(parent)
        self._project_root = state.validated_project_root(project_root)
        self._base_url = base_url.rstrip("/")
        self._server_process: Optional[subprocess.Popen] = None
        self._turn_token = ""
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def configure(self, project_root: Path, base_url: str) -> None:
        if self._busy:
            raise RuntimeError("Agent 工作期间不能切换项目或服务地址。")
        self._project_root = state.validated_project_root(project_root)
        self._base_url = base_url.rstrip("/")

    def _emit(self, kind: str, **values) -> None:
        payload = {"kind": kind}
        payload.update(values)
        self.event.emit(payload)

    def health(self, timeout=2) -> bool:
        try:
            result = _json_request(
                f"{self._base_url}/api/health",
                timeout=timeout,
            )
            return bool(
                result.get("ok")
                and result.get("service") == "camo-auto-gen-livery-agent"
                and int(result.get("apiVersion") or 0) >= 2
            )
        except Exception:
            return False

    def start_service(self) -> None:
        self._emit("service_connecting")
        threading.Thread(target=self._start_service_worker, daemon=True).start()

    def _start_service_worker(self) -> None:
        try:
            if self.health():
                self._emit("service_ready")
                return
            parsed = urllib.parse.urlparse(self._base_url)
            port = parsed.port or 8766
            server = self._project_root / "livery-workbench" / "server.py"
            if not server.is_file():
                raise FileNotFoundError(f"Agent 服务脚本不存在：{server}")
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._server_process = subprocess.Popen(
                [
                    _python_for_server(self._project_root),
                    str(server),
                    "--port",
                    str(port),
                    "--no-browser",
                ],
                cwd=str(self._project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            for _ in range(100):
                if self.health():
                    self._emit("service_ready")
                    return
                if self._server_process.poll() is not None:
                    raise RuntimeError("Agent 服务启动后立即退出。")
                time.sleep(0.15)
            raise TimeoutError("等待 Agent 服务启动超时。")
        except Exception as exc:
            self._emit("error", message=str(exc))

    def send(self, message: str, context_payload: Dict) -> None:
        text = message.strip()
        if not text:
            raise ValueError("请输入 Agent 设计要求。")
        if self._busy:
            raise RuntimeError("Agent 正在处理当前任务。")
        if not self.health():
            raise RuntimeError("请先连接 Agent 服务。")
        self._busy = True
        self._turn_token = uuid.uuid4().hex
        token = self._turn_token
        self._emit("agent_started")
        threading.Thread(
            target=self._send_worker,
            args=(text, context_payload, token),
            daemon=True,
        ).start()

    def _send_worker(self, message: str, context_payload: Dict, token: str) -> None:
        try:
            initial = _json_request(
                f"{self._base_url}/api/agent/events?since=0",
                timeout=5,
            )
            cursor = int(initial.get("cursor") or 0)
            _json_request(
                f"{self._base_url}/api/agent/message",
                payload={"message": message, "context": context_payload},
                timeout=45,
            )
            response_parts = []
            reported_approvals = set()
            deadline = time.time() + 900
            while time.time() < deadline:
                if token != self._turn_token:
                    return
                status = _json_request(
                    f"{self._base_url}/api/agent/events?since={cursor}",
                    timeout=10,
                )
                cursor = int(status.get("cursor") or cursor)
                for event in status.get("events") or []:
                    kind = event.get("kind")
                    if kind == "assistant_delta":
                        response_parts.append(str(event.get("text") or ""))
                        if len(response_parts) % 8 == 0:
                            self._emit(
                                "agent_progress",
                                message="".join(response_parts)[-1800:],
                            )
                    elif kind == "activity":
                        self._emit(
                            "agent_activity",
                            message=str(event.get("title") or ""),
                        )
                    elif kind == "approval_resolved":
                        self._emit("approval_cleared")
                    elif kind == "error":
                        raise RuntimeError(
                            str(event.get("message") or "Agent 执行失败")
                        )
                    elif kind == "turn_completed":
                        self._busy = False
                        self._turn_token = ""
                        self._emit(
                            "agent_done",
                            message="".join(response_parts).strip(),
                            status=str(event.get("status") or "completed"),
                        )
                        return
                for approval in status.get("pendingApprovals") or []:
                    approval_id = str(approval.get("id") or "")
                    if approval_id and approval_id not in reported_approvals:
                        reported_approvals.add(approval_id)
                        self._emit("agent_approval", approval=approval)
                if status.get("status") == "error":
                    raise RuntimeError(str(status.get("error") or "Agent 执行失败"))
                time.sleep(0.7)
            raise TimeoutError("Agent 处理超过 15 分钟。")
        except Exception as exc:
            if token == self._turn_token:
                self._busy = False
                self._turn_token = ""
                self._emit("error", message=str(exc))

    def _post_async(self, endpoint: str, payload: Dict, success_kind: str) -> None:
        def worker():
            try:
                result = _json_request(
                    f"{self._base_url}{endpoint}",
                    payload=payload,
                    timeout=20,
                )
                self._emit(success_kind, result=result)
            except Exception as exc:
                self._emit("error", message=str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def interrupt(self) -> None:
        self._post_async("/api/agent/interrupt", {}, "agent_interrupted")

    def reset(self) -> None:
        self._turn_token = ""
        self._busy = False
        self._post_async("/api/agent/reset", {}, "agent_reset")

    def respond_approval(self, approval_id: str, decision: str) -> None:
        if not approval_id:
            raise ValueError("没有待处理的 Agent 审批。")
        self._post_async(
            "/api/agent/approval",
            {"approvalId": approval_id, "decision": decision},
            "approval_sent",
        )

    def stop_service(self) -> bool:
        self._turn_token = ""
        self._busy = False
        process = self._server_process
        self._server_process = None
        if process is None or process.poll() is not None:
            return False
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        self._emit("service_stopped")
        return True

    def close(self) -> None:
        self.stop_service()
