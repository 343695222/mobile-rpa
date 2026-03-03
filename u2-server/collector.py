"""DataCollector — 数据采集调度器。

按优先级协调多种采集策略（api > rpa_copy > rpa_ocr），
优先复用已保存脚本，采集成功后自动保存新脚本。

返回标准化结果:
    {
        "success": bool,
        "items": [...],
        "strategy": str,
        "scriptId": str | None,
        "error": str | None,
    }
"""

from __future__ import annotations

import logging
from typing import Any

from device import DeviceManager
from navigator import Navigator
from script_store import ScriptStore
from strategies import ApiStrategy, RpaCopyStrategy, RpaOcrStrategy
from vision import GlmVisionClient

logger = logging.getLogger(__name__)

# Valid strategy names in priority order
STRATEGY_PRIORITY = ["api", "rpa_copy", "rpa_ocr"]


class DataCollector:
    """数据采集调度器：脚本优先，策略按优先级回退。"""

    STRATEGY_PRIORITY = STRATEGY_PRIORITY

    def __init__(
        self,
        device_manager: DeviceManager,
        navigator: Navigator,
        script_store: ScriptStore,
        vision_client: GlmVisionClient,
    ) -> None:
        self.device_manager = device_manager
        self.navigator = navigator
        self.script_store = script_store
        self.vision_client = vision_client

        # Instantiate strategies with their required dependencies
        self._strategies: dict[str, Any] = {
            "api": ApiStrategy(),
            "rpa_copy": RpaCopyStrategy(device_manager, navigator),
            "rpa_ocr": RpaOcrStrategy(device_manager, navigator, vision_client),
        }

    async def collect(
        self,
        device_id: str,
        app: str,
        data_type: str,
        query: str = "",
        force_strategy: str | None = None,
    ) -> dict[str, Any]:
        """执行数据采集。

        流程:
        1. 若指定 force_strategy，验证后仅使用该策略
        2. 查找已有有效脚本 → 按脚本执行
        3. 无脚本 → 按优先级依次探索

        Returns:
            标准化结果 dict，包含 success/items/strategy/scriptId/error
        """
        # ── 验证 force_strategy ──────────────────────────────
        if force_strategy is not None:
            if force_strategy not in self._strategies:
                return self._result(
                    success=False,
                    strategy=force_strategy,
                    error=f"无效的策略: {force_strategy}，支持: {', '.join(STRATEGY_PRIORITY)}",
                )

        # ── 确定要尝试的策略列表 ──────────────────────────────
        strategies_to_try = (
            [force_strategy] if force_strategy else list(STRATEGY_PRIORITY)
        )

        # ── 1. 脚本优先：查找已有有效脚本 ────────────────────
        existing_script = self.script_store.find(app, data_type)

        if existing_script is not None:
            script_strategy = existing_script.get("strategy", "")
            script_id = existing_script["id"]

            # 如果指定了 force_strategy 且脚本策略不匹配，跳过脚本
            if force_strategy is None or script_strategy == force_strategy:
                strategy_obj = self._strategies.get(script_strategy)
                if strategy_obj is not None:
                    logger.info(
                        "Using existing script %s (strategy=%s) for %s/%s",
                        script_id, script_strategy, app, data_type,
                    )
                    result = await strategy_obj.execute(device_id, existing_script)

                    if result.get("success"):
                        self.script_store.update_usage(script_id)
                        return self._result(
                            success=True,
                            items=result.get("items", []),
                            strategy=script_strategy,
                            script_id=script_id,
                        )

                    # 脚本执行失败 → 标记无效，继续探索
                    logger.warning(
                        "Script %s execution failed, marking invalid: %s",
                        script_id, result.get("error", ""),
                    )
                    self.script_store.mark_invalid(script_id)

        # ── 2. 无可用脚本（或脚本失败）→ 按优先级探索 ────────
        errors: list[str] = []

        for strategy_name in strategies_to_try:
            strategy_obj = self._strategies.get(strategy_name)
            if strategy_obj is None:
                continue

            logger.info(
                "Trying strategy '%s' for %s/%s", strategy_name, app, data_type,
            )

            try:
                result = await strategy_obj.explore(
                    device_id, app, data_type, query,
                )
            except Exception as exc:
                logger.error("Strategy '%s' raised exception: %s", strategy_name, exc)
                errors.append(f"{strategy_name}: {exc}")
                continue

            if result.get("success"):
                # 采集成功 → 保存脚本
                script_config = result.get("script_config", {})
                script_id = self.script_store.save(
                    app=app,
                    data_type=data_type,
                    strategy=strategy_name,
                    config=script_config,
                )
                logger.info(
                    "Strategy '%s' succeeded, saved script %s",
                    strategy_name, script_id,
                )
                return self._result(
                    success=True,
                    items=result.get("items", []),
                    strategy=strategy_name,
                    script_id=script_id,
                )

            # 策略失败，记录错误，继续下一个
            err_msg = result.get("error", "未知错误")
            errors.append(f"{strategy_name}: {err_msg}")
            logger.info("Strategy '%s' failed: %s", strategy_name, err_msg)

        # ── 所有策略均失败 ───────────────────────────────────
        attempted = ", ".join(strategies_to_try)
        error_detail = "; ".join(errors) if errors else "无详细错误"
        return self._result(
            success=False,
            strategy=strategies_to_try[-1] if strategies_to_try else "",
            error=f"所有策略均失败 (尝试: {attempted}): {error_detail}",
        )

    # ── 结果构造 ─────────────────────────────────────────────

    @staticmethod
    def _result(
        *,
        success: bool,
        items: list | None = None,
        strategy: str = "",
        script_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """构造标准化采集结果。"""
        return {
            "success": success,
            "items": items if items is not None else [],
            "strategy": strategy,
            "scriptId": script_id,
            "error": error,
        }
