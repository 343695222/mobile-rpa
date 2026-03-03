"""Tests for TrafficCapture module."""

import json
import os
import tempfile
from pathlib import Path

import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from traffic_capture import TrafficCapture, TrafficRecord


def _make_record(
    url: str = "https://api.example.com/data",
    method: str = "GET",
    content_type: str = "application/json",
    response_body: str = '{"ok": true}',
    response_status: int = 200,
    duration_ms: float = 100.0,
) -> TrafficRecord:
    return TrafficRecord(
        url=url,
        method=method,
        request_headers={"User-Agent": "test"},
        request_body=None,
        response_status=response_status,
        response_headers={"Content-Type": content_type},
        response_body=response_body,
        content_type=content_type,
        timestamp="2025-01-01T00:00:00Z",
        duration_ms=duration_ms,
    )


class TestTrafficRecord:
    def test_is_api_json(self):
        r = _make_record(content_type="application/json")
        assert r.is_api is True
        assert r.is_static is False

    def test_is_api_text_plain_with_json_body(self):
        r = _make_record(content_type="text/plain", response_body='{"data": 1}')
        assert r.is_api is True

    def test_is_api_text_plain_without_json_body(self):
        r = _make_record(content_type="text/plain", response_body="hello world")
        assert r.is_api is False

    def test_is_static_image(self):
        r = _make_record(content_type="image/png", response_body="")
        assert r.is_static is True
        assert r.is_api is False

    def test_is_static_css(self):
        r = _make_record(content_type="text/css", response_body="body{}")
        assert r.is_static is True

    def test_is_static_js(self):
        r = _make_record(content_type="application/javascript", response_body="var x=1")
        assert r.is_static is True


class TestTrafficCapture:
    def test_start_stop_recording(self):
        cap = TrafficCapture(data_dir=tempfile.mkdtemp())
        assert cap.is_recording is False
        cap.start_recording("test_platform", [])
        assert cap.is_recording is True
        assert cap.platform_name == "test_platform"
        records = cap.stop_recording()
        assert cap.is_recording is False
        assert records == []

    def test_add_record_while_recording(self):
        cap = TrafficCapture(data_dir=tempfile.mkdtemp())
        cap.start_recording("test", [])
        r = _make_record()
        assert cap.add_record(r) is True
        assert len(cap.get_records()) == 1

    def test_add_record_not_recording(self):
        cap = TrafficCapture(data_dir=tempfile.mkdtemp())
        r = _make_record()
        assert cap.add_record(r) is False
        assert len(cap.get_records()) == 0

    def test_domain_filter_accept(self):
        cap = TrafficCapture(data_dir=tempfile.mkdtemp())
        cap.start_recording("test", ["example.com"])
        r = _make_record(url="https://api.example.com/data")
        assert cap.add_record(r) is True

    def test_domain_filter_reject(self):
        cap = TrafficCapture(data_dir=tempfile.mkdtemp())
        cap.start_recording("test", ["example.com"])
        r = _make_record(url="https://other-site.com/data")
        assert cap.add_record(r) is False

    def test_domain_filter_case_insensitive(self):
        cap = TrafficCapture(data_dir=tempfile.mkdtemp())
        cap.start_recording("test", ["Example.COM"])
        r = _make_record(url="https://api.example.com/data")
        assert cap.add_record(r) is True

    def test_save_to_file(self):
        tmpdir = tempfile.mkdtemp()
        cap = TrafficCapture(data_dir=tmpdir)
        cap.start_recording("myplatform", [])
        cap.add_record(_make_record())
        cap.add_record(_make_record(url="https://api.example.com/other"))
        cap.stop_recording()
        filepath = cap.save_to_file()
        assert os.path.exists(filepath)
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 2
        assert data[0]["url"] == "https://api.example.com/data"

    def test_load_from_har(self):
        har_data = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "method": "GET",
                            "url": "https://api.jubaozhu.com/auctions",
                            "headers": [{"name": "Authorization", "value": "Bearer abc"}],
                        },
                        "response": {
                            "status": 200,
                            "headers": [{"name": "Content-Type", "value": "application/json"}],
                            "content": {
                                "mimeType": "application/json",
                                "text": '{"data": [{"id": 1}]}',
                            },
                        },
                        "startedDateTime": "2025-01-01T00:00:00Z",
                        "time": 150,
                    },
                    {
                        "request": {
                            "method": "GET",
                            "url": "https://cdn.jubaozhu.com/logo.png",
                            "headers": [],
                        },
                        "response": {
                            "status": 200,
                            "headers": [],
                            "content": {"mimeType": "image/png", "text": ""},
                        },
                        "startedDateTime": "2025-01-01T00:00:01Z",
                        "time": 50,
                    },
                ]
            }
        }
        tmpdir = tempfile.mkdtemp()
        har_path = os.path.join(tmpdir, "test.har")
        with open(har_path, "w", encoding="utf-8") as f:
            json.dump(har_data, f)

        cap = TrafficCapture(data_dir=tmpdir)
        records = cap.load_from_har(har_path)
        assert len(records) == 2
        assert records[0].url == "https://api.jubaozhu.com/auctions"
        assert records[0].method == "GET"
        assert records[0].response_status == 200
        assert records[0].is_api is True
        assert records[1].is_static is True

    def test_load_from_har_file_not_found(self):
        cap = TrafficCapture()
        with pytest.raises(FileNotFoundError):
            cap.load_from_har("/nonexistent/file.har")

    def test_get_stats(self):
        cap = TrafficCapture(data_dir=tempfile.mkdtemp())
        stats = cap.get_stats()
        assert stats["recording"] is False
        assert stats["record_count"] == 0
        cap.start_recording("test", ["example.com"])
        cap.add_record(_make_record())
        stats = cap.get_stats()
        assert stats["recording"] is True
        assert stats["record_count"] == 1
        assert stats["platform"] == "test"

    def test_clear(self):
        cap = TrafficCapture(data_dir=tempfile.mkdtemp())
        cap.start_recording("test", [])
        cap.add_record(_make_record())
        assert len(cap.get_records()) == 1
        cap.clear()
        assert len(cap.get_records()) == 0
        assert cap.is_recording is False
