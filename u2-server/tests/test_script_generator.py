"""Tests for ApiScriptGenerator module."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from traffic_analyzer import ApiEndpoint
from script_generator import ApiScriptGenerator


class MockScriptStore:
    """Mock ScriptStore for testing."""

    def __init__(self):
        self.saved = []
        self._counter = 0

    def save(self, app, data_type, strategy, config):
        self._counter += 1
        script_id = f"script_{self._counter}"
        self.saved.append({
            "id": script_id,
            "app": app,
            "data_type": data_type,
            "strategy": strategy,
            "config": config,
        })
        return script_id


def _make_endpoint(
    url_pattern="/v1/auctions",
    base_url="https://api.example.com",
    method="GET",
    auth_type="none",
    auth_headers=None,
    request_params=None,
    response_schema=None,
):
    return ApiEndpoint(
        url_pattern=url_pattern,
        base_url=base_url,
        method=method,
        auth_type=auth_type,
        auth_headers=auth_headers or [],
        request_params=request_params or {},
        response_sample='{"data": []}',
        response_schema=response_schema or {},
        sample_count=1,
        avg_duration_ms=100.0,
    )


class TestGenerate:
    def setup_method(self):
        self.store = MockScriptStore()
        self.gen = ApiScriptGenerator(self.store)

    def test_level1_api_script(self):
        ep = _make_endpoint()
        analysis = {"difficulty_level": 1, "recommended_strategy": "api", "purpose": "竞拍列表", "platform_name": "聚宝猪"}
        script = self.gen.generate(ep, analysis)
        assert script["strategy"] == "api"
        assert script["app"] == "聚宝猪"
        assert script["dataType"] == "竞拍列表"
        assert script["extraction"]["type"] == "api"
        assert "https://api.example.com/v1/auctions" in script["extraction"]["config"]["url"]

    def test_level2_api_with_auth(self):
        ep = _make_endpoint(auth_type="bearer", auth_headers=["Authorization"])
        analysis = {"difficulty_level": 2, "recommended_strategy": "api", "purpose": "竞拍详情", "platform_name": "聚宝猪"}
        script = self.gen.generate(ep, analysis)
        assert script["strategy"] == "api"
        assert "{{Authorization}}" in script["extraction"]["config"]["headers"]["Authorization"]
        assert "_auth_note" in script["extraction"]["config"]
        assert "_auth_type" in script["extraction"]["config"]

    def test_level3_rpa_script(self):
        ep = _make_endpoint(auth_type="custom_sign")
        analysis = {"difficulty_level": 3, "recommended_strategy": "rpa_ocr", "purpose": "出价记录", "platform_name": "聚宝猪"}
        script = self.gen.generate(ep, analysis)
        assert script["strategy"] == "rpa_ocr"
        assert script["extraction"]["type"] == "ocr"
        assert "出价记录" in script["extraction"]["config"]["extractPrompt"]

    def test_level4_rpa_script(self):
        ep = _make_endpoint()
        analysis = {"difficulty_level": 4, "recommended_strategy": "hybrid", "purpose": "交易数据"}
        script = self.gen.generate(ep, analysis)
        assert script["strategy"] == "rpa_ocr"

    def test_save_to_store(self):
        ep = _make_endpoint()
        analysis = {"difficulty_level": 1, "recommended_strategy": "api", "purpose": "列表", "platform_name": "test"}
        script = self.gen.generate(ep, analysis)
        script_id = self.gen.save_to_store(script)
        assert script_id == "script_1"
        assert len(self.store.saved) == 1
        assert self.store.saved[0]["app"] == "test"


class TestGuessDataPath:
    def test_data_list(self):
        schema = {"data": {"list": {"_type": "array"}}}
        assert ApiScriptGenerator._guess_data_path(schema) == "data.list"

    def test_data_items(self):
        schema = {"data": {"items": {"_type": "array"}}}
        assert ApiScriptGenerator._guess_data_path(schema) == "data.items"

    def test_data_array(self):
        schema = {"data": {"_type": "array", "_count": 10}}
        assert ApiScriptGenerator._guess_data_path(schema) == "data"

    def test_result_records(self):
        schema = {"result": {"records": {"_type": "array"}}}
        assert ApiScriptGenerator._guess_data_path(schema) == "result.records"

    def test_empty_schema(self):
        assert ApiScriptGenerator._guess_data_path({}) == ""

    def test_no_match(self):
        schema = {"code": {"_type": "int"}, "msg": {"_type": "str"}}
        assert ApiScriptGenerator._guess_data_path(schema) == ""
