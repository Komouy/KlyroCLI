"""
tests/test_model_crawler.py — Unit Tests for OfficialModelCrawler
"""

from __future__ import annotations

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from core.model_crawler import OfficialModelCrawler, _strip_html_to_text, get_model_crawler
import provider_manager


@pytest.fixture
def tmp_catalog_file(tmp_path):
    return str(tmp_path / "official_catalog.json")


@pytest.fixture
def crawler(tmp_catalog_file):
    return OfficialModelCrawler(catalog_file=tmp_catalog_file)


def test_strip_html_to_text():
    html = """
    <html>
      <head><script>alert('test')</script><style>.bad{color:red}</style></head>
      <body>
        <h1>Official Models</h1>
        <p>Available models: <b>llama-3.3-70b-versatile</b> and <i>gemini-2.5-flash</i>.</p>
      </body>
    </html>
    """
    text = _strip_html_to_text(html)
    assert "alert" not in text
    assert ".bad" not in text
    assert "Official Models" in text
    assert "llama-3.3-70b-versatile" in text


def test_crawler_fallback_to_static_when_api_and_docs_fail(crawler):
    with patch("urllib.request.urlopen", side_effect=Exception("Network down")):
        res = crawler.sync_provider("groq", timeout=1)
        assert res["success"] is True
        assert res["count"] > 0
        model_ids = [m["id"] for m in res["models"]]
        assert "llama-3.3-70b-versatile" in model_ids


def test_crawler_sync_openrouter_free_models(crawler):
    mock_payload = {
        "data": [
            {
                "id": "z-ai/glm-5.2:free",
                "name": "GLM 5.2",
                "pricing": {"prompt": "0", "completion": "0"},
                "context_length": 256000
            },
            {
                "id": "paid/model:standard",
                "name": "Paid Model",
                "pricing": {"prompt": "0.001", "completion": "0.002"},
                "context_length": 128000
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = crawler.sync_provider("openrouter", timeout=1)
        assert res["success"] is True
        assert res["count"] == 1
        assert res["models"][0]["id"] == "z-ai/glm-5.2:free"
        assert "100% Free" in res["models"][0]["desc"]


def test_crawler_filters_dead_models(crawler, tmp_path):
    from core.model_discovery import DeadModelManager
    dead_file = str(tmp_path / "dead.json")
    dead_mgr = DeadModelManager(file_path=dead_file)
    dead_mgr.evict("groq", "llama-3.3-70b-versatile", "Tested dead")
    crawler.dead_mgr = dead_mgr

    with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
        res = crawler.sync_provider("groq", timeout=1)
        model_ids = [m["id"] for m in res["models"]]
        assert "llama-3.3-70b-versatile" not in model_ids


def test_provider_manager_integrates_synced_models(crawler, tmp_path):
    # Seed crawler catalog
    crawler._catalog["groq"] = {
        "models": [{"id": "synced-mock-model", "desc": "★ Synced"}]
    }
    crawler._save_catalog()

    with patch("core.model_crawler.get_model_crawler", return_value=crawler):
        models = provider_manager.get_models_list("groq")
        assert len(models) == 1
        assert models[0]["id"] == "synced-mock-model"
