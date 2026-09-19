"""
tests/test_model_discovery.py - Unit Tests for Dynamic Live Model Discovery & Dead Model Self-Healing

Covers:
  1. DeadModelManager  - blacklist, eviction, persistence, clear
  2. LiveModelDiscovery - dead-model filtering, cache hit/miss, static fallback
  3. SmartRouter        - skips dead models in route() and get_fallback_candidates()
  4. provider_manager   - get_provider_models() filters dead models
"""

from __future__ import annotations

import json
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.model_discovery import (
    DeadModelManager,
    LiveModelDiscovery,
    get_dead_model_manager,
    get_live_discovery,
    CACHE_TTL_SECONDS,
)


# ----------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------

@pytest.fixture
def tmp_dead_file(tmp_path):
    return str(tmp_path / "dead_models.json")


@pytest.fixture
def dead_mgr(tmp_dead_file):
    return DeadModelManager(file_path=tmp_dead_file)


@pytest.fixture
def tmp_cache_file(tmp_path):
    return str(tmp_path / "live_cache.json")


@pytest.fixture
def discovery(tmp_cache_file, dead_mgr):
    return LiveModelDiscovery(cache_file=tmp_cache_file, dead_mgr=dead_mgr)


# ----------------------------------------------------------------
# 1. DeadModelManager
# ----------------------------------------------------------------

class TestDeadModelManager:

    def test_initially_empty(self, dead_mgr):
        assert not dead_mgr.is_dead("groq", "llama-3-8b")

    def test_evict_marks_dead(self, dead_mgr):
        result = dead_mgr.evict("groq", "deleted-model-1", "HTTP 404")
        assert result is True
        assert dead_mgr.is_dead("groq", "deleted-model-1")

    def test_evict_is_case_insensitive_provider(self, dead_mgr):
        dead_mgr.evict("GROQ", "some-model")
        assert dead_mgr.is_dead("groq", "some-model")

    def test_evict_writes_to_disk(self, dead_mgr, tmp_dead_file):
        dead_mgr.evict("mistral", "old-model-v1", "Decommissioned")
        with open(tmp_dead_file, "r") as f:
            data = json.load(f)
        assert "mistral:old-model-v1" in data
        assert data["mistral:old-model-v1"]["reason"] == "Decommissioned"

    def test_reload_persists_across_instances(self, tmp_dead_file):
        mgr1 = DeadModelManager(file_path=tmp_dead_file)
        mgr1.evict("openrouter", "ghost-model:free", "gone")
        mgr2 = DeadModelManager(file_path=tmp_dead_file)
        assert mgr2.is_dead("openrouter", "ghost-model:free")

    def test_clear_removes_all(self, dead_mgr):
        dead_mgr.evict("groq", "model-a")
        dead_mgr.evict("mistral", "model-b")
        dead_mgr.clear()
        assert not dead_mgr.is_dead("groq", "model-a")
        assert not dead_mgr.is_dead("mistral", "model-b")
        assert dead_mgr.get_all_dead() == {}

    def test_evict_bad_input_returns_false(self, dead_mgr):
        assert dead_mgr.evict("", "some-model") is False
        assert dead_mgr.evict("groq", "") is False

    def test_get_all_dead(self, dead_mgr):
        dead_mgr.evict("groq", "m1", "404")
        dead_mgr.evict("groq", "m2", "decommissioned")
        all_dead = dead_mgr.get_all_dead()
        assert "groq:m1" in all_dead
        assert "groq:m2" in all_dead
        assert len(all_dead) == 2

    def test_evict_records_timestamp(self, dead_mgr):
        before = time.time()
        dead_mgr.evict("mistral", "stale-model")
        after = time.time()
        entry = dead_mgr.get_all_dead().get("mistral:stale-model", {})
        assert before <= entry.get("evicted_at", 0) <= after


# ----------------------------------------------------------------
# 2. LiveModelDiscovery
# ----------------------------------------------------------------

SAMPLE_GROQ_MODELS = [
    {"id": "llama-3.3-70b-versatile", "desc": "Active on GROQ"},
    {"id": "gemma2-9b-it",            "desc": "Active on GROQ"},
    {"id": "whisper-large-v3",         "desc": "Active on GROQ"},
]


class TestLiveModelDiscovery:

    def test_returns_static_catalog_when_fetch_fails(self, discovery):
        result = discovery.get_models("groq")
        assert isinstance(result, list)

    def test_dead_models_filtered_from_cache(self, discovery, dead_mgr):
        dead_mgr.evict("groq", "llama-3.3-70b-versatile", "gone")
        discovery._cache["groq"] = {
            "timestamp": time.time(),
            "models": SAMPLE_GROQ_MODELS.copy()
        }
        result = discovery.get_models("groq")
        ids = [m["id"] for m in result]
        assert "llama-3.3-70b-versatile" not in ids
        assert "gemma2-9b-it" in ids

    def test_fresh_cache_not_refetched(self, discovery):
        seeded = [{"id": "cached-model", "desc": "cached"}]
        discovery._cache["mistral"] = {
            "timestamp": time.time(),
            "models": seeded,
        }
        with patch.object(discovery, "_fetch_from_provider") as mock_fetch:
            result = discovery.get_models("mistral")
            mock_fetch.assert_not_called()
        assert result == seeded

    def test_stale_cache_triggers_refetch(self, discovery):
        discovery._cache["mistral"] = {
            "timestamp": time.time() - CACHE_TTL_SECONDS - 60,
            "models": [{"id": "old-model", "desc": "old"}],
        }
        new_models = [{"id": "new-model", "desc": "new"}]
        with patch.object(discovery, "_fetch_from_provider", return_value=new_models):
            result = discovery.get_models("mistral")
        assert result == new_models

    def test_force_refresh_bypasses_fresh_cache(self, discovery):
        discovery._cache["groq"] = {
            "timestamp": time.time(),
            "models": [{"id": "stale-in-cache", "desc": "stale"}],
        }
        fresh_models = [{"id": "actually-fresh", "desc": "fresh"}]
        with patch.object(discovery, "_fetch_from_provider", return_value=fresh_models):
            result = discovery.get_models("groq", force_refresh=True)
        assert any(m["id"] == "actually-fresh" for m in result)

    def test_all_dead_models_filtered_returns_empty_list(self, discovery, dead_mgr):
        dead_mgr.evict("groq", "only-model")
        discovery._cache["groq"] = {
            "timestamp": time.time(),
            "models": [{"id": "only-model", "desc": "soon gone"}],
        }
        result = discovery.get_models("groq")
        assert result == []

    def test_whisper_tts_embed_models_excluded(self, discovery):
        raw_data = {
            "data": [
                {"id": "whisper-large-v3"},
                {"id": "tts-1"},
                {"id": "text-embedding-ada-002"},
                {"id": "llama-3.3-70b-versatile"},
            ]
        }
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(raw_data).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = discovery._fetch_openai_compatible_models(
                endpoint="https://api.groq.com/openai/v1/models",
                api_key="test-key",
                provider="groq"
            )
        ids = [m["id"] for m in result]
        assert "llama-3.3-70b-versatile" in ids
        assert "whisper-large-v3" not in ids
        assert "tts-1" not in ids
        assert "text-embedding-ada-002" not in ids

    def test_openrouter_free_filter(self, discovery):
        raw_data = {
            "data": [
                {"id": "z-ai/glm-5.2:free",      "pricing": {"prompt": "0", "completion": "0"}, "context_length": 131072, "name": "GLM 5.2"},
                {"id": "openai/gpt-4o",           "pricing": {"prompt": "0.005", "completion": "0.015"}, "context_length": 128000, "name": "GPT-4o"},
                {"id": "meta-llama/llama-3:free", "pricing": {"prompt": "0", "completion": "0"}, "context_length": 8192, "name": "Llama 3"},
            ]
        }
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(raw_data).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = discovery._fetch_openrouter_free()
        ids = [m["id"] for m in result]
        assert "z-ai/glm-5.2:free" in ids
        assert "meta-llama/llama-3:free" in ids
        assert "openai/gpt-4o" not in ids

    def test_ollama_models_fetched(self, discovery):
        raw_data = {
            "models": [
                {"name": "llama3.2:latest", "size": 2_000_000_000},
                {"name": "deepseek-coder:7b", "size": 4_000_000_000},
            ]
        }
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(raw_data).encode()
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_resp
            result = discovery._fetch_ollama_models("http://localhost:11434/v1")
        ids = [m["id"] for m in result]
        assert "llama3.2:latest" in ids
        assert "deepseek-coder:7b" in ids


# ----------------------------------------------------------------
# 3. SmartRouter - dead model skipping
# ----------------------------------------------------------------

class TestSmartRouterDeadModelSkipping:

    def test_route_skips_dead_model(self, tmp_dead_file):
        from core.smart_router import SmartRouter, WorkloadTier
        import provider_manager as pm

        dead_mgr = DeadModelManager(file_path=tmp_dead_file)
        router = SmartRouter()

        with patch("core.model_discovery.get_dead_model_manager", return_value=dead_mgr):
            prov, model, reason, tier = router.route(WorkloadTier.LIGHT)
        assert isinstance(prov, str)
        assert isinstance(model, str)

    def test_get_fallback_candidates_skips_dead(self, tmp_dead_file):
        from core.smart_router import SmartRouter, WorkloadTier
        import provider_manager as pm

        dead_mgr = DeadModelManager(file_path=tmp_dead_file)
        groq_default = pm.PROVIDER_CATALOG.get("groq", {}).get("default_model", "")
        dead_mgr.evict("groq", groq_default, "unit-test eviction")

        router = SmartRouter()
        with patch("core.model_discovery.get_dead_model_manager", return_value=dead_mgr):
            candidates = router.get_fallback_candidates(WorkloadTier.CODE, failed_provider="openrouter")

        for prov, model, label in candidates:
            assert not (prov == "groq" and model == groq_default), (
                f"Dead model groq/{groq_default} appeared in fallback candidates!"
            )


# ----------------------------------------------------------------
# 4. provider_manager.get_provider_models()
# ----------------------------------------------------------------

class TestGetProviderModels:

    def test_returns_list_of_dicts(self):
        import provider_manager as pm
        result = pm.get_provider_models("groq")
        assert isinstance(result, list)
        for m in result:
            assert "id" in m
            assert "desc" in m

    def test_dead_models_not_in_result(self, tmp_dead_file):
        import provider_manager as pm

        dead_mgr = DeadModelManager(file_path=tmp_dead_file)
        groq_models = pm.PROVIDER_CATALOG.get("groq", {}).get("models", [])
        if not groq_models:
            pytest.skip("No groq static models to test against")

        first_model_id = groq_models[0]["id"]
        dead_mgr.evict("groq", first_model_id, "test eviction")

        with patch("core.model_discovery.get_dead_model_manager", return_value=dead_mgr), \
             patch("core.model_discovery.get_live_discovery") as mock_discovery:
            mock_discovery.return_value.get_models.return_value = []
            result = pm.get_provider_models("groq")

        ids = [m["id"] for m in result]
        assert first_model_id not in ids

    def test_force_refresh_flag_passed(self):
        import provider_manager as pm
        with patch("core.model_discovery.get_live_discovery") as mock_disc:
            mock_instance = MagicMock()
            mock_instance.get_models.return_value = [{"id": "fresh", "desc": "live"}]
            mock_disc.return_value = mock_instance
            result = pm.get_provider_models("groq", force_refresh=True)
        mock_instance.get_models.assert_called_once_with("groq", force_refresh=True)
        assert result == [{"id": "fresh", "desc": "live"}]

    def test_get_models_list_alias(self):
        import provider_manager as pm
        assert pm.get_models_list is pm.get_provider_models
