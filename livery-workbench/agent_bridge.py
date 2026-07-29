from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from copy import deepcopy
from pathlib import Path
from queue import Empty, Queue
from typing import Any


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_codex_executable() -> str | None:
    """Resolve Codex even when a DCC host starts with a reduced PATH."""
    explicit = os.environ.get("CAMO_CODEX_PATH") or os.environ.get("CODEX_PATH")
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit).expanduser())

    discovered = shutil.which("codex")
    if discovered:
        candidates.append(Path(discovered))

    if os.name == "nt":
        user_home = Path.home()
        extension_roots = (
            user_home / ".vscode" / "extensions",
            user_home / ".vscode-insiders" / "extensions",
            user_home / ".cursor" / "extensions",
        )
        extension_candidates: list[Path] = []
        for extension_root in extension_roots:
            if not extension_root.is_dir():
                continue
            extension_candidates.extend(
                extension_root.glob(
                    "openai.chatgpt-*/bin/windows-x86_64/codex.exe"
                )
            )
        extension_candidates.sort(
            key=lambda path: path.stat().st_mtime if path.is_file() else 0,
            reverse=True,
        )
        candidates.extend(extension_candidates)

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            continue
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return str(resolved)
    return None


class AgentBridge:
    """Small JSON-RPC bridge between the workbench and Codex app-server."""

    def __init__(self, project_root: Path, skill_path: Path) -> None:
        self.project_root = project_root.resolve()
        self.skill_path = skill_path.resolve()
        self.codex_path = find_codex_executable()
        self.process: subprocess.Popen[str] | None = None
        self.thread_id = ""
        self.turn_id = ""
        self.model = ""
        self.status = "offline"
        self.last_error = ""
        self.last_context: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []
        self.proposals: dict[str, dict[str, Any]] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self.stderr_tail: list[str] = []
        self.sequence = 0
        self.request_id = 0
        self.pending_rpc: dict[str, Queue[dict[str, Any]]] = {}
        self.state_lock = threading.RLock()
        self.write_lock = threading.Lock()
        self.start_lock = threading.Lock()

    def capabilities(self) -> dict[str, Any]:
        logged_in = False
        auth_label = "未登录"
        if self.codex_path:
            try:
                completed = subprocess.run(
                    [self.codex_path, "login", "status"],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=6,
                    creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                output = (completed.stdout or completed.stderr or "").strip()
                logged_in = completed.returncode == 0 and "logged in" in output.lower()
                if "chatgpt" in output.lower():
                    auth_label = "ChatGPT"
                elif logged_in:
                    auth_label = "已登录"
            except (OSError, subprocess.TimeoutExpired):
                pass
        return {
            "available": bool(self.codex_path),
            "loggedIn": logged_in,
            "authLabel": auth_label,
            "codexPath": self.codex_path or "",
            "skill": "blender-vehicle-livery",
            "status": self.status,
        }

    def _emit(self, kind: str, **payload: Any) -> dict[str, Any]:
        with self.state_lock:
            self.sequence += 1
            event = {
                "seq": self.sequence,
                "kind": kind,
                "time": time.time(),
                **payload,
            }
            self.events.append(event)
            if len(self.events) > 1600:
                self.events = self.events[-1200:]
            return event

    def _send(self, message: dict[str, Any]) -> None:
        process = self.process
        if not process or process.poll() is not None or not process.stdin:
            raise RuntimeError("Codex Agent 进程未运行")
        line = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self.write_lock:
            process.stdin.write(line)
            process.stdin.flush()

    def _rpc(self, method: str, params: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        with self.state_lock:
            self.request_id += 1
            request_id = self.request_id
            wait_queue: Queue[dict[str, Any]] = Queue(maxsize=1)
            self.pending_rpc[str(request_id)] = wait_queue
        try:
            self._send({"id": request_id, "method": method, "params": params})
            try:
                response = wait_queue.get(timeout=timeout)
            except Empty as exc:
                raise TimeoutError(f"Codex 请求超时：{method}") from exc
            if response.get("error"):
                error = response["error"]
                message = error.get("message") if isinstance(error, dict) else str(error)
                raise RuntimeError(message or f"Codex 请求失败：{method}")
            return response.get("result") or {}
        finally:
            with self.state_lock:
                self.pending_rpc.pop(str(request_id), None)

    def _reader_loop(self) -> None:
        process = self.process
        if not process or not process.stdout:
            return
        try:
            for raw_line in process.stdout:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    message = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                self._handle_message(message)
        finally:
            return_code = process.poll()
            with self.state_lock:
                if self.process is process:
                    self.status = "offline"
                    self.thread_id = ""
                    self.turn_id = ""
            if return_code not in (None, 0, -15):
                self._emit("error", message=f"Codex Agent 已退出（{return_code}）")

    def _stderr_loop(self) -> None:
        process = self.process
        if not process or not process.stderr:
            return
        for raw_line in process.stderr:
            line = raw_line.rstrip()
            if not line:
                continue
            with self.state_lock:
                self.stderr_tail.append(line)
                self.stderr_tail = self.stderr_tail[-80:]

    def _handle_message(self, message: dict[str, Any]) -> None:
        request_key = str(message.get("id")) if "id" in message else ""
        method = str(message.get("method") or "")
        if request_key and not method:
            with self.state_lock:
                wait_queue = self.pending_rpc.get(request_key)
            if wait_queue:
                wait_queue.put(message)
            return
        if request_key and method:
            threading.Thread(
                target=self._handle_server_request,
                args=(message,),
                daemon=True,
            ).start()
            return
        if method:
            self._handle_notification(method, message.get("params") or {})

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "item/agentMessage/delta":
            delta = str(params.get("delta") or "")
            if delta:
                self._emit("assistant_delta", text=delta, turnId=params.get("turnId"))
            return
        if method == "turn/started":
            turn = params.get("turn") or {}
            with self.state_lock:
                self.turn_id = str(turn.get("id") or self.turn_id)
                self.status = "running"
            self._emit("turn_started", turnId=self.turn_id)
            return
        if method == "turn/completed":
            turn = params.get("turn") or {}
            status = str(turn.get("status") or "completed")
            error = turn.get("error")
            recoverable_terminal = status in {"completed", "interrupted", "cancelled", "canceled"}
            with self.state_lock:
                self.status = "ready" if recoverable_terminal else "error"
                self.turn_id = ""
                self.last_error = json.dumps(error, ensure_ascii=False) if error else ""
            self._emit("turn_completed", status=status, error=error)
            return
        if method in {"item/started", "item/completed"}:
            item = params.get("item") or {}
            item_type = str(item.get("type") or "")
            if item_type in {"commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall"}:
                self._emit(
                    "activity",
                    phase="started" if method.endswith("started") else "completed",
                    itemType=item_type,
                    title=self._activity_title(item),
                )
            return
        if method == "error":
            error = params.get("error") or params
            message = error.get("message") if isinstance(error, dict) else str(error)
            message = message or "Codex Agent 出错"
            if "reconnecting" in message.lower() or "retrying" in message.lower():
                self._emit("activity", phase="started", itemType="connection", title=message)
            else:
                self.last_error = message
                self._emit("error", message=self.last_error)

    @staticmethod
    def _activity_title(item: dict[str, Any]) -> str:
        item_type = str(item.get("type") or "")
        if item_type == "commandExecution":
            command = item.get("command") or item.get("aggregatedOutput") or "本地命令"
            if isinstance(command, list):
                command = " ".join(map(str, command))
            return str(command)[:180]
        if item_type == "fileChange":
            return "准备工作区文件修改"
        if item_type == "mcpToolCall":
            return str(item.get("tool") or item.get("server") or "MCP 工具")
        return str(item.get("tool") or "工作台工具")

    def _handle_server_request(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = str(message.get("method") or "")
        params = message.get("params") or {}
        try:
            if method == "item/tool/call":
                result = self._handle_dynamic_tool(params)
                self._send({"id": request_id, "result": result})
                return
            if method in {
                "item/commandExecution/requestApproval",
                "item/fileChange/requestApproval",
                "execCommandApproval",
                "applyPatchApproval",
            }:
                approval_id = str(request_id)
                approval = {
                    "id": approval_id,
                    "rawId": request_id,
                    "method": method,
                    "title": "命令执行审批" if "command" in method.lower() or "exec" in method.lower() else "文件修改审批",
                    "reason": str(params.get("reason") or params.get("message") or "Agent 请求继续执行此操作"),
                    "command": self._approval_command(params),
                    "status": "pending",
                }
                with self.state_lock:
                    self.approvals[approval_id] = approval
                    self.status = "waiting_approval"
                self._emit("approval", approval=deepcopy(approval))
                return
            self._send(
                {
                    "id": request_id,
                    "error": {"code": -32601, "message": f"工作台暂不支持 Agent 请求：{method}"},
                }
            )
        except Exception as exc:
            self._send({"id": request_id, "error": {"code": -32000, "message": str(exc)}})

    @staticmethod
    def _approval_command(params: dict[str, Any]) -> str:
        command = params.get("command") or params.get("cmd") or params.get("changes") or ""
        if isinstance(command, list):
            command = " ".join(map(str, command))
        if isinstance(command, dict):
            command = json.dumps(command, ensure_ascii=False)
        return str(command)[:1200]

    def _handle_dynamic_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        tool = str(params.get("tool") or "")
        arguments = params.get("arguments") or {}
        if tool in {"workbench_get_state", "livery_surface_get_state"}:
            text = json.dumps(self.last_context, ensure_ascii=False, indent=2)
            return {"success": True, "contentItems": [{"type": "inputText", "text": text}]}
        if tool == "workbench_propose_layout_changes":
            if not isinstance(arguments, dict):
                raise ValueError("布局提案必须是 JSON 对象")
            operations = arguments.get("operations") or []
            if not isinstance(operations, list) or not operations:
                raise ValueError("布局提案至少需要一个 operation")
            if len(operations) > 48:
                raise ValueError("一次布局提案最多包含 48 项操作")
            proposal_id = uuid.uuid4().hex[:12]
            proposal = {
                "id": proposal_id,
                "summary": str(arguments.get("summary") or "Agent 布局调整提案")[:500],
                "operations": deepcopy(operations),
                "status": "pending",
                "createdAt": time.time(),
            }
            with self.state_lock:
                self.proposals[proposal_id] = proposal
            self._emit("proposal", proposal=deepcopy(proposal))
            return {
                "success": True,
                "contentItems": [
                    {
                        "type": "inputText",
                        "text": f"布局提案 {proposal_id} 已显示在工作台，等待用户应用或放弃。",
                    }
                ],
            }
        raise ValueError(f"未知工作台工具：{tool}")

    def _dynamic_tools(self) -> list[dict[str, Any]]:
        operation_schema = {
            "type": "object",
            "required": ["op"],
            "properties": {
                "op": {
                    "type": "string",
                    "enum": [
                        "update_layer",
                        "add_asset",
                        "add_text",
                        "delete_layer",
                        "reorder_layer",
                        "set_material",
                        "select_layer",
                        "set_view",
                    ],
                },
                "layerId": {"type": "string"},
                "assetPath": {"type": "string"},
                "index": {"type": "integer"},
                "view": {"type": "string", "enum": ["design", "model", "result"]},
                "changes": {"type": "object", "additionalProperties": True},
                "properties": {"type": "object", "additionalProperties": True},
            },
            "additionalProperties": False,
        }
        return [
            {
                "type": "function",
                "name": "workbench_get_state",
                "description": "Read the current live livery editor state, selected model/guide/layer, material values, and available project assets.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "type": "function",
                "name": "livery_surface_get_state",
                "description": "Read the current Blender Surface Studio capture, framed screen rectangle, hit mesh faces, saved view matrices, source asset, and output contract.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "type": "function",
                "name": "workbench_propose_layout_changes",
                "description": "Propose reversible live-editor changes. The workbench shows an approval card and applies nothing until the user clicks Apply.",
                "inputSchema": {
                    "type": "object",
                    "required": ["summary", "operations"],
                    "properties": {
                        "summary": {"type": "string"},
                        "operations": {"type": "array", "minItems": 1, "maxItems": 48, "items": operation_schema},
                    },
                    "additionalProperties": False,
                },
            },
        ]

    def ensure_started(self) -> dict[str, Any]:
        with self.start_lock:
            if self.process and self.process.poll() is None and self.thread_id:
                return self.get_status()
            if not self.codex_path:
                raise FileNotFoundError("未找到 Codex CLI，请先安装或启用 Codex")
            self.shutdown(clear_events=False)
            self.status = "connecting"
            self.last_error = ""
            self.process = subprocess.Popen(
                [self.codex_path, "app-server", "--stdio"],
                cwd=self.project_root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            threading.Thread(target=self._reader_loop, daemon=True).start()
            threading.Thread(target=self._stderr_loop, daemon=True).start()
            self._rpc(
                "initialize",
                {
                    "clientInfo": {
                        "name": "vehicle-livery-workbench",
                        "title": "Vehicle Livery Workbench",
                        "version": "1.1.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
                timeout=20,
            )
            self._send({"method": "initialized", "params": {}})
            thread = self._rpc(
                "thread/start",
                {
                    "cwd": str(self.project_root),
                    "runtimeWorkspaceRoots": [str(self.project_root)],
                    "approvalPolicy": "on-request",
                    "approvalsReviewer": "user",
                    "sandbox": "workspace-write",
                    "ephemeral": True,
                    "personality": "pragmatic",
                    "dynamicTools": self._dynamic_tools(),
                    "developerInstructions": self._developer_instructions(),
                },
                timeout=30,
            )
            self.thread_id = str((thread.get("thread") or {}).get("id") or "")
            self.model = str(thread.get("model") or "")
            if not self.thread_id:
                raise RuntimeError("Codex 未返回有效会话 ID")
            self.status = "ready"
            self._emit(
                "connected",
                message="Codex Agent 已连接，并加载 blender-vehicle-livery Skill",
                model=self.model,
            )
            return self.get_status()

    @staticmethod
    def _developer_instructions() -> str:
        return (
            "You are embedded in a local vehicle-livery application that may be the legacy browser workbench, Blender Surface Studio, or Adobe Substance 3D Painter Livery Studio. Reply in concise Chinese unless the user asks otherwise. "
            "Use the supplied blender-vehicle-livery skill for all livery decisions. Inspect the supplied live application context with workbench_get_state or livery_surface_get_state. "
            "For changes to an open browser draft, never edit its state file directly: call workbench_propose_layout_changes and let the user approve the proposal card. "
            "For Blender Surface Studio, keep the whole conversation and approvals in Blender and never instruct the user to open the browser workbench. "
            "When a framed session exists, use the supplied screenshot, frame, actual hit-face record, and output contract; do not convert it back into a directional or six-face projector. "
            "For Substance Painter, keep the whole conversation and approvals in Painter, use its screenshot selection as a visual boundary, and create one flat texture suitable for the requested native Fill projection mode. Inspect context.reference_assets as optional visual inputs for identity, palette, motifs, texture language, and composition; never treat a reference as the requested output or auto-apply target unless the user explicitly asks. A painter_resource record without a local image path provides metadata, not readable pixels. Painter 10.1+ can import the returned texture and create an editable Layer Stack Fill layer directly. "
            "When no frame exists, treat the request as standalone reusable texture creation. Create or process a flat aspect-safe image under the requested project directory, keep important subject parts inside any physical frame, and end with the exact LIVERY_ASSET marker when a file is ready so the host can add it to its project or asset library. "
            "Keep image proportions uniform and treat Blender render output as authoritative. "
            "Do not start subagents. Ask clarifying questions in the normal assistant response rather than request-user-input tools. "
            "Only modify project files, export, or render when the user's message explicitly asks you to execute that action."
        )

    def send_message(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        message = message.strip()
        if not message:
            raise ValueError("请输入 Agent 指令")
        if len(message) > 12000:
            raise ValueError("单条 Agent 指令不得超过 12000 字符")
        try:
            self.ensure_started()
        except Exception as exc:
            with self.state_lock:
                self.status = "error"
                self.last_error = str(exc)
            self._emit("error", message=str(exc))
            raise
        with self.state_lock:
            if self.status in {"running", "waiting_approval"}:
                raise RuntimeError("Agent 正在处理当前指令，请先等待、审批或停止")
            self.last_context = deepcopy(context)
            thread_id = self.thread_id
            self.status = "running"
        self._emit("user_message", text=message)
        try:
            result = self._rpc(
                "turn/start",
                {
                    "threadId": thread_id,
                    "cwd": str(self.project_root),
                    "runtimeWorkspaceRoots": [str(self.project_root)],
                    "additionalContext": {
                        "livery-workbench-live-state": {
                            "kind": "application",
                            "value": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
                        }
                    },
                    "input": [
                        {"type": "skill", "name": "blender-vehicle-livery", "path": str(self.skill_path)},
                        {"type": "text", "text": message},
                    ],
                },
                timeout=30,
            )
        except Exception as exc:
            with self.state_lock:
                self.status = "error"
                self.turn_id = ""
                self.last_error = str(exc)
            self._emit("error", message=str(exc))
            raise
        self.turn_id = str((result.get("turn") or {}).get("id") or self.turn_id)
        return {"ok": True, "threadId": self.thread_id, "turnId": self.turn_id}

    def interrupt(self) -> dict[str, Any]:
        with self.state_lock:
            thread_id = self.thread_id
            turn_id = self.turn_id
        if not thread_id or not turn_id:
            return {"ok": True, "interrupted": False}
        self._rpc("turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=12)
        return {"ok": True, "interrupted": True}

    def respond_approval(self, approval_id: str, decision: str) -> dict[str, Any]:
        with self.state_lock:
            approval = self.approvals.get(str(approval_id))
        if not approval or approval.get("status") != "pending":
            raise KeyError("审批请求不存在或已处理")
        accepted = decision in {"accept", "acceptForSession"}
        result_decision = "acceptForSession" if decision == "acceptForSession" else "accept" if accepted else "decline"
        self._send({"id": approval["rawId"], "result": {"decision": result_decision}})
        with self.state_lock:
            approval["status"] = "accepted" if accepted else "declined"
            self.status = "running" if self.turn_id else "ready"
        self._emit("approval_resolved", approvalId=approval_id, decision=result_decision)
        return {"ok": True, "decision": result_decision}

    def resolve_proposal(self, proposal_id: str, accepted: bool) -> dict[str, Any]:
        with self.state_lock:
            proposal = self.proposals.get(str(proposal_id))
            if not proposal or proposal.get("status") != "pending":
                raise KeyError("布局提案不存在或已处理")
            proposal["status"] = "accepted" if accepted else "declined"
        self._emit("proposal_resolved", proposalId=proposal_id, accepted=bool(accepted))
        return {"ok": True, "accepted": bool(accepted)}

    def get_status(self, since: int = 0) -> dict[str, Any]:
        with self.state_lock:
            events = [deepcopy(event) for event in self.events if int(event["seq"]) > int(since)]
            return {
                "available": bool(self.codex_path),
                "status": self.status,
                "threadId": self.thread_id,
                "turnId": self.turn_id,
                "model": self.model,
                "cursor": self.sequence,
                "events": events,
                "pendingApprovals": [
                    deepcopy(item) for item in self.approvals.values() if item.get("status") == "pending"
                ],
                "pendingProposals": [
                    deepcopy(item) for item in self.proposals.values() if item.get("status") == "pending"
                ],
                "error": self.last_error,
            }

    def reset(self) -> dict[str, Any]:
        self.shutdown(clear_events=True)
        self._emit("system", message="已开始新的 Agent 会话")
        return self.get_status()

    def shutdown(self, *, clear_events: bool = False) -> None:
        process = self.process
        self.process = None
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
        with self.state_lock:
            self.thread_id = ""
            self.turn_id = ""
            self.model = ""
            self.status = "offline"
            self.pending_rpc.clear()
            self.approvals.clear()
            self.proposals.clear()
            if clear_events:
                self.events.clear()
                self.sequence = 0
