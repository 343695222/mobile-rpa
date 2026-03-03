"""ScriptValidator — 脚本验证器。

逐一执行已保存的采集脚本，检查是否仍能成功采集数据。
验证失败的脚本标记为无效，验证成功的脚本更新验证时间。
"""

from __future__ import annotations

import logging
from typing import Any

from script_store import ScriptStore

logger = logging.getLogger(__name__)

# Strategy name → class mapping is resolved at init time via injected instances.


class ScriptValidator:
    """验证已保存脚本的有效性。"""

    def __init__(
        self,
        script_store: ScriptStore,
        strategies: dict[str, Any],
    ) -> None:
        """
        Parameters
        ----------
        script_store : ScriptStore
            脚本仓库实例。
        strategies : dict[str, Any]
            策略名称到策略实例的映射，例如
            {"api": api_strategy, "rpa_copy": rpa_copy_strategy, "rpa_ocr": rpa_ocr_strategy}
        """
        self._store = script_store
        self._strategies = strategies

    async def validate_all(self, device_id: str) -> dict[str, Any]:
        """逐一验证所有脚本，返回验证摘要。

        Returns
        -------
        dict with keys:
            total    – 验证的脚本总数
            success  – 验证成功数
            failure  – 验证失败数
            results  – 每个脚本的验证详情列表
        """
        summaries = self._store.list_all()
        results: list[dict[str, Any]] = []
        success_count = 0
        failure_count = 0

        for summary in summaries:
            script_id = summary["id"]
            script = self._store._read(script_id)
            if script is None:
                # 文件可能已被删除
                failure_count += 1
                results.append(
                    {"id": script_id, "valid": False, "error": "脚本文件不存在"}
                )
                continue

            valid = await self.validate_one(device_id, script)
            if valid:
                success_count += 1
            else:
                failure_count += 1
            results.append({"id": script_id, "valid": valid})

        return {
            "total": len(summaries),
            "success": success_count,
            "failure": failure_count,
            "results": results,
        }

    async def validate_one(self, device_id: str, script: dict) -> bool:
        """执行单个脚本并检查结果。

        成功时更新 lastValidatedAt，失败时标记脚本为无效。

        Returns
        -------
        bool – True 表示验证通过，False 表示验证失败。
        """
        script_id = script.get("id", "")
        strategy_name = script.get("strategy", "")
        strategy = self._strategies.get(strategy_name)

        if strategy is None:
            logger.warning("未知策略 %s，脚本 %s 验证失败", strategy_name, script_id)
            self._store.mark_invalid(script_id)
            return False

        try:
            result = await strategy.execute(device_id, script)
            if result.get("success"):
                self._store.update_validation(script_id, True)
                return True
            else:
                logger.info(
                    "脚本 %s 验证失败: %s",
                    script_id,
                    result.get("error", "执行返回失败"),
                )
                self._store.mark_invalid(script_id)
                return False
        except Exception as exc:
            logger.error("脚本 %s 验证异常: %s", script_id, exc)
            self._store.mark_invalid(script_id)
            return False
