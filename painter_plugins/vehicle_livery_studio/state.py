from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union


SETTINGS_SCHEMA = "painter-livery-studio-settings/v3"
CAPTURE_SCHEMA = "painter-livery-capture/v1"
LIBRARY_SCHEMA = "painter-livery-resource-library/v1"
RUNTIME_SCHEMA = "painter-livery-runtime/v1"
PROJECT_MARKERS = (
    Path("livery-workbench") / "server.py",
    Path("skills") / "blender-vehicle-livery" / "SKILL.md",
)


def is_project_root(path: Path) -> bool:
    try:
        root = path.resolve()
    except (OSError, RuntimeError):
        return False
    return all((root / marker).is_file() for marker in PROJECT_MARKERS)


def _candidate_ancestors(path: Path):
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return
    yield resolved
    yield from resolved.parents


def find_project_root() -> Optional[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("CAMO_PROJECT_ROOT")
    if configured:
        candidates.append(Path(configured))
    candidates.extend(_candidate_ancestors(Path.cwd()))
    candidates.extend(_candidate_ancestors(Path(__file__).parent))
    user_home = Path.home()
    candidates.extend(
        (
            user_home / "Camo_Auto_Gen",
            user_home / "Documents" / "Camo_Auto_Gen",
        )
    )
    if os.name == "nt":
        candidates.extend(
            Path(f"{letter}:\\Camo_Auto_Gen")
            for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"
        )

    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(str(candidate))
        if key in seen:
            continue
        seen.add(key)
        if is_project_root(candidate):
            return candidate.resolve()
    return None


def validated_project_root(value: Union[str, Path]) -> Path:
    root = Path(value).expanduser().resolve()
    if not is_project_root(root):
        expected = "、".join(str(marker) for marker in PROJECT_MARKERS)
        raise FileNotFoundError(
            f"项目目录无效：{root}。该目录必须包含：{expected}"
        )
    return root


def resolve_project_path(
    project_root: Union[str, Path],
    value: Union[str, Path],
    *,
    create_parent: bool = False,
) -> Path:
    root = validated_project_root(project_root)
    candidate = Path(value).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"路径必须位于项目目录内：{root}") from exc
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def safe_slug(value: str, fallback: str = "painter-resource") -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", value.strip()).strip("-_")
    return cleaned[:64] or fallback


def timestamp_id(label: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    return f"{stamp}-{safe_slug(label)}"


def _atomic_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def load_settings(project_root: Union[str, Path]) -> dict[str, Any]:
    root = validated_project_root(project_root)
    path = root / "painter-livery-studio" / "state" / "settings.json"
    defaults = {
        "schema": SETTINGS_SCHEMA,
        "project_root": str(root),
        "agent_url": "http://127.0.0.1:8766",
        "prompt": "",
        "auto_import": True,
        "auto_create_layer": True,
        "projection_mode": "Planar",
        "import_project": True,
        "import_shelf": True,
        "asset_name": "",
        "image_path": "",
        "last_capture": "",
        "last_resource": {},
        "reference_assets": [],
    }
    if not path.is_file():
        return defaults
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return defaults
    if not isinstance(loaded, dict):
        return defaults
    # Preserve user values from v1 while migrating to the current schema.
    if str(loaded.get("schema") or "").startswith("painter-livery-studio-settings/"):
        defaults.update(loaded)
    defaults["schema"] = SETTINGS_SCHEMA
    defaults["project_root"] = str(root)
    return defaults


def save_settings(project_root: Union[str, Path], values: dict[str, Any]) -> Path:
    root = validated_project_root(project_root)
    payload = dict(values)
    payload["schema"] = SETTINGS_SCHEMA
    payload["project_root"] = str(root)
    payload["updated_at"] = datetime.now().astimezone().isoformat()
    return _atomic_json(
        root / "painter-livery-studio" / "state" / "settings.json",
        payload,
    )


def capture_paths(
    project_root: Union[str, Path],
    capture_id: str,
) -> tuple[Path, Path, Path]:
    root = validated_project_root(project_root)
    directory = root / "painter-livery-studio" / "state" / "captures"
    directory.mkdir(parents=True, exist_ok=True)
    return (
        directory / f"{capture_id}-window.png",
        directory / f"{capture_id}-selection.png",
        directory / f"{capture_id}.json",
    )


def write_capture(project_root: Union[str, Path], payload: dict[str, Any]) -> Path:
    capture_id = safe_slug(str(payload["id"]))
    _, _, session_path = capture_paths(project_root, capture_id)
    record = dict(payload)
    record["schema"] = CAPTURE_SCHEMA
    record["updated_at"] = datetime.now().astimezone().isoformat()
    return _atomic_json(session_path, record)


def append_library_record(
    project_root: Union[str, Path],
    record: dict[str, Any],
) -> Path:
    root = validated_project_root(project_root)
    path = root / "assets" / "painter-library" / "index.json"
    payload: dict[str, Any] = {"schema": LIBRARY_SCHEMA, "resources": []}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if (
                loaded.get("schema") == LIBRARY_SCHEMA
                and isinstance(loaded.get("resources"), list)
            ):
                payload = loaded
        except (OSError, ValueError, TypeError):
            pass
    payload["resources"].append(record)
    payload["updated_at"] = datetime.now().astimezone().isoformat()
    return _atomic_json(path, payload)


def write_runtime_status(
    project_root: Union[str, Path],
    *,
    status: str,
    version: str,
    detail: str = "",
) -> Path:
    root = validated_project_root(project_root)
    payload = {
        "schema": RUNTIME_SCHEMA,
        "status": status,
        "plugin_version": version,
        "detail": detail,
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    return _atomic_json(
        root / "painter-livery-studio" / "state" / "runtime.json",
        payload,
    )


def versioned_path(directory: Path, stem: str, suffix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    revision = 1
    while True:
        candidate = directory / f"{stem}-r{revision}{suffix}"
        if not candidate.exists():
            return candidate
        revision += 1
