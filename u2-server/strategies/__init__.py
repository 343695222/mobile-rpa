"""采集策略包 — 提供四种数据采集策略。

策略优先级: api > midscene > rpa_copy > rpa_ocr
"""

from .api_strategy import ApiStrategy
from .base import BaseStrategy
from .midscene_strategy import MidsceneStrategy
from .rpa_copy_strategy import RpaCopyStrategy
from .rpa_ocr_strategy import RpaOcrStrategy

__all__ = [
    "BaseStrategy",
    "ApiStrategy",
    "MidsceneStrategy",
    "RpaCopyStrategy",
    "RpaOcrStrategy",
]
