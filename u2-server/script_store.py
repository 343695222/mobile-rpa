"""ScriptStore — 脚本仓库，管理已学习的采集脚本。

脚本以独立 JSON 文件存储在 u2-server/scripts/ 目录，文件名为 {script_id}.json。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


class ScriptStore:
    """采集脚本的 CRUD 管理器。"""

    def __init__(self, scripts_dir: str | None = None):
        if scripts_dir is None:
            scripts_dir = str(Path(__file__).parent / "scripts")
        self._dir = Path(scripts_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── helpers ──────────────────────────────────────────────

    def _path(self, script_id: str) -> Path:
        return self._dir / f"{script_id}.json"

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _read(self, script_id: str) -> dict | None:
        p = self._path(script_id)
        if not p.exists():
            return None
        return self.deserialize(p.read_text(encoding="utf-8"))

    def _write(self, script: dict) -> None:
        p = self._path(script["id"])
        p.write_text(self.serialize(script), encoding="utf-8")

    # ── CRUD ─────────────────────────────────────────────────

    def save(self, app: str, data_type: str, strategy: str, config: dict) -> str:
        """创建并持久化一个新脚本，返回生成的 UUID。"""
        script_id = str(uuid.uuid4())
        now = self._now_iso()
        script: dict = {
            "id": script_id,
            "app": app,
            "dataType": data_type,
            "strategy": strategy,
            "navigation": config.get("navigation", []),
            "extraction": config.get("extraction", {}),
            "metadata": {
                "createdAt": now,
                "lastUsedAt": now,
                "lastValidatedAt": now,
                "useCount": 0,
                "isValid": True,
            },
        }
        self._write(script)
        return script_id

    def find(self, app: str, data_type: str) -> dict | None:
        """按 app + dataType 查找有效脚本（isValid=True）。"""
        for f in self._dir.glob("*.json"):
            script = self.deserialize(f.read_text(encoding="utf-8"))
            if (
                script.get("app") == app
                and script.get("dataType") == data_type
                and script.get("metadata", {}).get("isValid", False)
            ):
                return script
        return None

    def find_navigation(self, app: str, target_page: str) -> dict | None:
        """按 app 和目标页面查找导航脚本。

        匹配逻辑：dataType 等于 target_page 且脚本有效。
        """
        for f in self._dir.glob("*.json"):
            script = self.deserialize(f.read_text(encoding="utf-8"))
            if (
                script.get("app") == app
                and script.get("dataType") == target_page
                and script.get("metadata", {}).get("isValid", False)
            ):
                return script
        return None

    def list_all(self) -> list[dict]:
        """返回所有脚本的摘要（包括无效脚本）。"""
        results: list[dict] = []
        for f in self._dir.glob("*.json"):
            script = self.deserialize(f.read_text(encoding="utf-8"))
            results.append(
                {
                    "id": script["id"],
                    "app": script["app"],
                    "dataType": script["dataType"],
                    "strategy": script["strategy"],
                    "isValid": script.get("metadata", {}).get("isValid", True),
                }
            )
        return results

    def delete(self, script_id: str) -> bool:
        """删除指定脚本文件，成功返回 True。"""
        p = self._path(script_id)
        if p.exists():
            p.unlink()
            return True
        return False

    # ── 状态更新 ─────────────────────────────────────────────

    def mark_invalid(self, script_id: str) -> None:
        """将脚本标记为无效。"""
        script = self._read(script_id)
        if script is None:
            return
        script["metadata"]["isValid"] = False
        self._write(script)

    def update_usage(self, script_id: str) -> None:
        """递增 useCount 并更新 lastUsedAt。"""
        script = self._read(script_id)
        if script is None:
            return
        script["metadata"]["useCount"] += 1
        script["metadata"]["lastUsedAt"] = self._now_iso()
        self._write(script)

    def update_validation(self, script_id: str, valid: bool) -> None:
        """更新验证状态和 lastValidatedAt。"""
        script = self._read(script_id)
        if script is None:
            return
        script["metadata"]["isValid"] = valid
        script["metadata"]["lastValidatedAt"] = self._now_iso()
        self._write(script)

    # ── 序列化 ───────────────────────────────────────────────

    def serialize(self, script: dict) -> str:
        """dict → JSON 字符串。"""
        return json.dumps(script, ensure_ascii=False, indent=2)

    def deserialize(self, json_str: str) -> dict:
        """JSON 字符串 → dict。"""
        return json.loads(json_str)
