"""Tests for TrafficAnalyzer module."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Optional

from traffic_capture import TrafficRecord
from traffic_analyzer import TrafficAnalyzer, ApiEndpoint, AnalysisResult


def _make_record(
    url: str = "https://api.example.com/v1/auctions",
    method: str = "GET",
    content_type: str = "application/json",
    response_body: str = '{"code": 0, "data": [{"id": 1, "title": "test"}]}',
    request_headers: Optional[dict] = None,
    request_body: Optional[str] = None,
    duration_ms: float = 100.0,
) -> TrafficRecord:
    return TrafficRecord(
        url=url,
        method=method,
        request_headers=request_headers or {"User-Agent": "test"},
        request_body=request_body,
        response_status=200,
        response_headers={"Content-Type": content_type},
        response_body=response_body,
        content_type=content_type,
        timestamp="2025-01-01T00:00:00Z",
        duration_ms=duration_ms,
    )


class TestClassifyRequests:
    def setup_method(self):
        self.analyzer = TrafficAnalyzer()

    def test_classify_json_api(self):
        records = [_make_record(content_type="application/json")]
        result = self.analyzer.classify_requests(records)
        assert len(result["api"]) == 1
        assert len(result["page"]) == 0
        assert len(result["static"]) == 0

    def test_classify_html_page(self):
        records = [_make_record(content_type="text/html", response_body="<html></html>")]
        result = self.analyzer.classify_requests(records)
        assert len(result["page"]) == 1

    def test_classify_static_image(self):
        records = [_make_record(content_type="image/png", response_body="")]
        result = self.analyzer.classify_requests(records)
        assert len(result["static"]) == 1

    def test_classify_static_css(self):
        records = [_make_record(content_type="text/css", response_body="body{}")]
        result = self.analyzer.classify_requests(records)
        assert len(result["static"]) == 1

    def test_classify_unlabeled_json(self):
        """Response body starts with { but content-type is not json."""
        records = [_make_record(content_type="text/html", response_body='{"data": 1}')]
        # text/html but body is JSON → should be classified as api
        result = self.analyzer.classify_requests(records)
        # html in content_type → page
        assert len(result["page"]) == 1

    def test_classify_unlabeled_json_no_html(self):
        """No content-type hint, but body is JSON."""
        records = [_make_record(content_type="application/octet-stream", response_body='{"data": 1}')]
        result = self.analyzer.classify_requests(records)
        assert len(result["api"]) == 1

    def test_classify_json_array(self):
        records = [_make_record(content_type="application/octet-stream", response_body='[{"id": 1}]')]
        result = self.analyzer.classify_requests(records)
        assert len(result["api"]) == 1

    def test_classify_mixed(self):
        records = [
            _make_record(url="https://api.example.com/data", content_type="application/json"),
            _make_record(url="https://example.com/page", content_type="text/html", response_body="<html>"),
            _make_record(url="https://cdn.example.com/logo.png", content_type="image/png", response_body=""),
            _make_record(url="https://cdn.example.com/style.css", content_type="text/css", response_body=""),
        ]
        result = self.analyzer.classify_requests(records)
        assert len(result["api"]) == 1
        assert len(result["page"]) == 1
        assert len(result["static"]) == 2


class TestDetectAuthType:
    def setup_method(self):
        self.analyzer = TrafficAnalyzer()

    def test_bearer_token(self):
        r = _make_record(request_headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9"})
        auth_type, headers = self.analyzer.detect_auth_type(r)
        assert auth_type == "bearer"
        assert "Authorization" in headers

    def test_cookie_auth(self):
        r = _make_record(request_headers={"Cookie": "session_id=abc123def456ghi789"})
        auth_type, headers = self.analyzer.detect_auth_type(r)
        assert auth_type == "cookie"
        assert "Cookie" in headers

    def test_custom_sign(self):
        r = _make_record(request_headers={"x-sign": "abc123", "timestamp": "1234567890"})
        auth_type, headers = self.analyzer.detect_auth_type(r)
        assert auth_type == "custom_sign"
        assert "x-sign" in headers

    def test_no_auth(self):
        r = _make_record(request_headers={"User-Agent": "test"})
        auth_type, headers = self.analyzer.detect_auth_type(r)
        assert auth_type == "none"
        assert headers == []

    def test_short_cookie_ignored(self):
        """Short cookies (< 20 chars) are not considered auth."""
        r = _make_record(request_headers={"Cookie": "a=b"})
        auth_type, headers = self.analyzer.detect_auth_type(r)
        assert auth_type == "none"

    def test_x_token(self):
        r = _make_record(request_headers={"x-token": "some-long-token-value"})
        auth_type, headers = self.analyzer.detect_auth_type(r)
        assert auth_type == "unknown"
        assert "x-token" in headers


class TestExtractEndpoints:
    def setup_method(self):
        self.analyzer = TrafficAnalyzer()

    def test_single_endpoint(self):
        records = [_make_record()]
        endpoints = self.analyzer.extract_endpoints(records)
        assert len(endpoints) == 1
        assert endpoints[0].url_pattern == "/v1/auctions"
        assert endpoints[0].method == "GET"
        assert endpoints[0].sample_count == 1

    def test_dedup_same_path(self):
        """Multiple requests to same path should be grouped."""
        records = [
            _make_record(url="https://api.example.com/v1/auctions?page=1"),
            _make_record(url="https://api.example.com/v1/auctions?page=2"),
        ]
        endpoints = self.analyzer.extract_endpoints(records)
        assert len(endpoints) == 1
        assert endpoints[0].sample_count == 2

    def test_normalize_numeric_ids(self):
        """Numeric path segments should be replaced with {id}."""
        records = [
            _make_record(url="https://api.example.com/v1/auctions/123"),
            _make_record(url="https://api.example.com/v1/auctions/456"),
        ]
        endpoints = self.analyzer.extract_endpoints(records)
        assert len(endpoints) == 1
        assert endpoints[0].url_pattern == "/v1/auctions/{id}"
        assert endpoints[0].sample_count == 2

    def test_different_methods_separate(self):
        records = [
            _make_record(url="https://api.example.com/v1/auctions", method="GET"),
            _make_record(url="https://api.example.com/v1/auctions", method="POST"),
        ]
        endpoints = self.analyzer.extract_endpoints(records)
        assert len(endpoints) == 2

    def test_extract_query_params(self):
        records = [_make_record(url="https://api.example.com/v1/auctions?page=1&size=20")]
        endpoints = self.analyzer.extract_endpoints(records)
        assert endpoints[0].request_params.get("page") == "1"
        assert endpoints[0].request_params.get("size") == "20"

    def test_extract_body_params(self):
        records = [_make_record(
            method="POST",
            request_body='{"keyword": "猪", "page": 1}',
        )]
        endpoints = self.analyzer.extract_endpoints(records)
        assert endpoints[0].request_params.get("keyword") == "猪"

    def test_response_sample_truncated(self):
        long_body = json.dumps({"data": "x" * 5000})
        records = [_make_record(response_body=long_body)]
        endpoints = self.analyzer.extract_endpoints(records)
        assert len(endpoints[0].response_sample) <= 2000


class TestExtractResponseSchema:
    def setup_method(self):
        self.analyzer = TrafficAnalyzer()

    def test_simple_object(self):
        schema = self.analyzer.extract_response_schema('{"code": 0, "msg": "ok"}')
        assert schema["code"]["_type"] == "int"
        assert schema["msg"]["_type"] == "str"

    def test_nested_object(self):
        body = '{"code": 0, "data": {"id": 1, "name": "test"}}'
        schema = self.analyzer.extract_response_schema(body)
        assert "data" in schema
        assert schema["data"]["id"]["_type"] == "int"

    def test_array_response(self):
        body = '{"data": [{"id": 1}, {"id": 2}]}'
        schema = self.analyzer.extract_response_schema(body)
        assert schema["data"]["_type"] == "array"
        assert schema["data"]["_count"] == 2

    def test_empty_array(self):
        body = '{"data": []}'
        schema = self.analyzer.extract_response_schema(body)
        assert schema["data"]["_type"] == "array"
        assert schema["data"]["_count"] == 0

    def test_non_json(self):
        schema = self.analyzer.extract_response_schema("not json")
        assert schema == {"_type": "non-json"}

    def test_none_body(self):
        schema = self.analyzer.extract_response_schema(None)
        assert schema == {}

    def test_max_depth(self):
        body = '{"a": {"b": {"c": {"d": {"e": 1}}}}}'
        schema = self.analyzer.extract_response_schema(body)
        # depth 3 should stop recursing
        assert "_type" in schema["a"]["b"]["c"]


class TestAnalyze:
    def setup_method(self):
        self.analyzer = TrafficAnalyzer()

    def test_full_analysis(self):
        records = [
            _make_record(url="https://api.jubaozhu.com/v1/auctions", content_type="application/json"),
            _make_record(url="https://api.jubaozhu.com/v1/auctions/123", content_type="application/json"),
            _make_record(url="https://www.jubaozhu.com/index.html", content_type="text/html", response_body="<html>"),
            _make_record(url="https://cdn.jubaozhu.com/logo.png", content_type="image/png", response_body=""),
        ]
        result = self.analyzer.analyze(records, "聚宝猪")
        assert result.platform_name == "聚宝猪"
        assert result.total_requests == 4
        assert len(result.api_endpoints) >= 1
        assert len(result.page_requests) == 1
        assert result.static_resources >= 1
        assert "api.jubaozhu.com" in result.domains

    def test_empty_records(self):
        result = self.analyzer.analyze([], "empty")
        assert result.total_requests == 0
        assert result.api_endpoints == []
