"""Tests for DataMapper module."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_mapper import DataMapper


class TestTransform:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mapper = DataMapper(config_dir=self.tmpdir)

    def test_basic_field_mapping(self):
        self.mapper._platform = "test"
        self.mapper._config = {
            "field_mapping": {
                "auction_id": "id",
                "pig_count": "quantity",
                "start_price": "price",
            },
            "type_conversions": {},
        }
        raw = [{"auction_id": "A001", "pig_count": "50", "start_price": "1500.00", "extra": "ignored"}]
        result = self.mapper.transform(raw)
        assert len(result) == 1
        assert result[0]["id"] == "A001"
        assert result[0]["quantity"] == "50"
        assert result[0]["price"] == "1500.00"
        assert "extra" not in result[0]
        assert result[0]["_source_platform"] == "test"

    def test_type_conversion_int(self):
        self.mapper._platform = "test"
        self.mapper._config = {
            "field_mapping": {"count": "quantity"},
            "type_conversions": {"quantity": "int"},
        }
        raw = [{"count": "50"}]
        result = self.mapper.transform(raw)
        assert result[0]["quantity"] == 50

    def test_type_conversion_float(self):
        self.mapper._platform = "test"
        self.mapper._config = {
            "field_mapping": {"price": "amount"},
            "type_conversions": {"amount": "float"},
        }
        raw = [{"price": "1500.50"}]
        result = self.mapper.transform(raw)
        assert result[0]["amount"] == 1500.50

    def test_type_conversion_bool(self):
        self.mapper._platform = "test"
        self.mapper._config = {
            "field_mapping": {"active": "is_active"},
            "type_conversions": {"is_active": "bool"},
        }
        raw = [{"active": "true"}, {"active": "0"}, {"active": "yes"}]
        result = self.mapper.transform(raw)
        assert result[0]["is_active"] is True
        assert result[1]["is_active"] is False
        assert result[2]["is_active"] is True

    def test_type_conversion_date(self):
        self.mapper._platform = "test"
        self.mapper._config = {
            "field_mapping": {"created": "date"},
            "type_conversions": {"date": "date"},
        }
        raw = [{"created": "2025/03/15"}]
        result = self.mapper.transform(raw)
        assert result[0]["date"] == "2025-03-15"

    def test_nested_field_access(self):
        self.mapper._platform = "test"
        self.mapper._config = {
            "field_mapping": {"data.auction.id": "auction_id", "data.auction.price": "price"},
            "type_conversions": {},
        }
        raw = [{"data": {"auction": {"id": "A001", "price": 1500}}}]
        result = self.mapper.transform(raw)
        assert result[0]["auction_id"] == "A001"
        assert result[0]["price"] == "1500"  # default type is string

    def test_missing_field_skipped(self):
        self.mapper._platform = "test"
        self.mapper._config = {
            "field_mapping": {"name": "title", "missing_field": "other"},
            "type_conversions": {},
        }
        raw = [{"name": "test"}]
        result = self.mapper.transform(raw)
        assert result[0]["title"] == "test"
        assert "other" not in result[0]

    def test_empty_input(self):
        self.mapper._platform = "test"
        self.mapper._config = {"field_mapping": {}, "type_conversions": {}}
        result = self.mapper.transform([])
        assert result == []


class TestConfig:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mapper = DataMapper(config_dir=self.tmpdir)

    def test_load_creates_default(self):
        config = self.mapper.load_config("新平台")
        assert config["platform"] == "新平台"
        assert "field_mapping" in config
        # Check file was created
        config_path = os.path.join(self.tmpdir, "新平台.json")
        assert os.path.exists(config_path)

    def test_load_existing_config(self):
        # Write a config file first
        config_path = os.path.join(self.tmpdir, "聚宝猪.json")
        custom_config = {
            "platform": "聚宝猪",
            "field_mapping": {"id": "auction_id"},
            "type_conversions": {"auction_id": "string"},
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(custom_config, f, ensure_ascii=False)

        config = self.mapper.load_config("聚宝猪")
        assert config["field_mapping"]["id"] == "auction_id"

    def test_save_config(self):
        self.mapper.load_config("test_save")
        self.mapper._config["field_mapping"]["new_field"] = "mapped_field"
        path = self.mapper.save_config()
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["field_mapping"]["new_field"] == "mapped_field"


class TestGetNested:
    def test_simple_key(self):
        assert DataMapper._get_nested({"a": 1}, "a") == 1

    def test_nested_key(self):
        assert DataMapper._get_nested({"a": {"b": {"c": 3}}}, "a.b.c") == 3

    def test_missing_key(self):
        assert DataMapper._get_nested({"a": 1}, "b") is None

    def test_missing_nested(self):
        assert DataMapper._get_nested({"a": {"b": 1}}, "a.c") is None


class TestConvertType:
    def test_int_from_string(self):
        assert DataMapper._convert_type("42", "int") == 42

    def test_int_from_float_string(self):
        assert DataMapper._convert_type("42.7", "int") == 42

    def test_float_from_string(self):
        assert DataMapper._convert_type("3.14", "float") == 3.14

    def test_string_from_int(self):
        assert DataMapper._convert_type(42, "string") == "42"

    def test_none_value(self):
        assert DataMapper._convert_type(None, "int") is None

    def test_invalid_int(self):
        result = DataMapper._convert_type("not_a_number", "int")
        assert result == "not_a_number"  # Falls back to str
