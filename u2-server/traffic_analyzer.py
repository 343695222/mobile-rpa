"""TrafficAnalyzer — 流量分析器。

纯数据处理，零 AI 依赖。从原始流量记录中提取结构化的 API 接口信息。

功能：
- 请求分类（API / 页面 / 静态资源）
- API 端点提取与去重（URL 路径归一化）
- 鉴权方式检测（bearer / cookie / custom_sign / none）
- 响应 JSON schema 提取
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, parse_qs

from traffic_capture import TrafficRecord


@dataclass
class ApiEndpoint:
    """识别出的 API 端点"""

    url_pattern: str  # 归一化路径，如 /api/v1/auctions/{id}
    base_url: str  # https://api.example.com
    method: str  # GET / POST
    auth_type: str  # none / bearer / cookie / custom_sign / unknown
    auth_headers: list[str]  # 涉及鉴权的 header 名
    request_params: dict  # 参数名 → 示例值
    response_sample: str  # 响应体样本（截断到 2KB）
    response_schema: dict  # 响应 JSON 结构摘要
    sample_count: int  # 捕获到的样本数
    avg_duration_ms: float  # 平均响应时间


@dataclass
class AnalysisResult:
    """流量分析结果"""

    platform_name: str
    total_requests: int
    api_endpoints: list[ApiEndpoint]
    page_requests: list[str]  # HTML 页面 URL
    static_resources: int  # 静态资源数量
    domains: list[str]  # 涉及的域名


class TrafficAnalyzer:
    """流量分析器 — 从原始流量中提取结构化接口信息。"""

    # 常见鉴权相关 header（小写）
    AUTH_HEADERS = [
        "authorization", "token", "x-token", "x-access-token",
        "x-auth-token", "x-api-key", "cookie", "x-sign", "sign",
        "x-signature", "nonce", "timestamp", "x-timestamp",
    ]

    def analyze(self, records: list[TrafficRecord], platform_name: str = "") -> AnalysisResult:
        """分析流量记录，输出结构化结果。"""
        classified = self.classify_requests(records)
        endpoints = self.extract_endpoints(classified["api"])
        domains = sorted(set(
            urlparse(r.url).hostname
            for r in records
            if urlparse(r.url).hostname
        ))

        return AnalysisResult(
            platform_name=platform_name,
            total_requests=len(records),
            api_endpoints=endpoints,
            page_requests=[r.url for r in classified["page"]],
            static_resources=len(classified["static"]),
            domains=domains,
        )

    def classify_requests(self, records: list[TrafficRecord]) -> dict[str, list[TrafficRecord]]:
        """将请求分为 api / page / static 三类。"""
        result: dict[str, list[TrafficRecord]] = {"api": [], "page": [], "static": []}
        for r in records:
            if r.is_static:
                result["static"].append(r)
            elif r.is_api:
                result["api"].append(r)
            else:
                ct = r.content_type.lower()
                if "html" in ct:
                    result["page"].append(r)
                elif r.response_body and r.response_body.strip().startswith("{"):
                    # 没标 content-type 但返回 JSON
                    result["api"].append(r)
                elif r.response_body and r.response_body.strip().startswith("["):
                    result["api"].append(r)
                else:
                    result["static"].append(r)
        return result

    def extract_endpoints(self, api_records: list[TrafficRecord]) -> list[ApiEndpoint]:
        """从 API 请求中提取去重的端点信息。"""
        # 按 (method, base_url, normalized_path) 分组
        groups: dict[tuple[str, str, str], list[TrafficRecord]] = {}
        for r in api_records:
            parsed = urlparse(r.url)
            # 将路径中的纯数字段替换为 {id}
            path = re.sub(r"/\d+(?=/|$)", "/{id}", parsed.path)
            base_url = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port and parsed.port not in (80, 443):
                base_url += f":{parsed.port}"
            key = (r.method, base_url, path)
            groups.setdefault(key, []).append(r)

        endpoints: list[ApiEndpoint] = []
        for (method, base_url, path), recs in groups.items():
            sample = recs[0]
            auth_type, auth_hdrs = self.detect_auth_type(sample)
            schema = self.extract_response_schema(sample.response_body)

            # 提取请求参数
            parsed = urlparse(sample.url)
            params: dict = {}
            for k, v in parse_qs(parsed.query).items():
                params[k] = v[0] if v else ""
            if sample.request_body:
                try:
                    body_params = json.loads(sample.request_body)
                    if isinstance(body_params, dict):
                        params.update(body_params)
                except (json.JSONDecodeError, ValueError):
                    pass

            endpoints.append(ApiEndpoint(
                url_pattern=path,
                base_url=base_url,
                method=method,
                auth_type=auth_type,
                auth_headers=auth_hdrs,
                request_params=params,
                response_sample=(sample.response_body or "")[:2000],
                response_schema=schema,
                sample_count=len(recs),
                avg_duration_ms=sum(r.duration_ms for r in recs) / len(recs),
            ))

        return endpoints

    def detect_auth_type(self, record: TrafficRecord) -> tuple[str, list[str]]:
        """检测请求的鉴权方式。"""
        headers = {k.lower(): v for k, v in record.request_headers.items()}
        found_headers: list[str] = []

        # Bearer Token
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return "bearer", ["Authorization"]

        # Cookie
        if "cookie" in headers and len(headers["cookie"]) > 20:
            found_headers.append("Cookie")

        # 自定义签名 header
        sign_headers = [
            h for h in self.AUTH_HEADERS
            if h in headers and h not in ("cookie", "authorization")
        ]
        if sign_headers:
            found_headers.extend(sign_headers)
            if any(h in sign_headers for h in ["x-sign", "sign", "x-signature"]):
                return "custom_sign", found_headers

        if found_headers:
            return ("cookie" if "Cookie" in found_headers else "unknown"), found_headers

        return "none", []

    def extract_response_schema(self, body: str | None) -> dict:
        """提取 JSON 响应的结构摘要（key → type）。"""
        if not body:
            return {}
        try:
            data = json.loads(body)
            return self._schema_from_value(data, depth=0, max_depth=3)
        except (json.JSONDecodeError, ValueError):
            return {"_type": "non-json"}

    def _schema_from_value(self, value: object, depth: int, max_depth: int) -> dict:
        """递归提取 JSON 值的类型结构。"""
        if depth >= max_depth:
            return {"_type": type(value).__name__}
        if isinstance(value, dict):
            return {
                k: self._schema_from_value(v, depth + 1, max_depth)
                for k, v in list(value.items())[:20]
            }
        if isinstance(value, list):
            if value:
                return {
                    "_type": "array",
                    "_item": self._schema_from_value(value[0], depth + 1, max_depth),
                    "_count": len(value),
                }
            return {"_type": "array", "_count": 0}
        return {"_type": type(value).__name__}
