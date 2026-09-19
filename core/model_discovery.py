"""
core/model_discovery.py — Dynamic Live Model Discovery & Dead Model Self-Healing

1. Dead Model Eviction:
   Persists dead / 404 / deprecated models in .klyro/dead_models.json so they are
   permanently blacklisted and excluded from SmartRouter and autocomplete.

2. Live Discovery:
   Queries live /models endpoints for OpenRouter, Groq, Mistral, and local Ollama
   (/api/tags) to maintain an accurate, fresh catalog of genuinely available models.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from typing import Optional, Dict, List, Any

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".klyro")
DEAD_MODELS_FILE = os.path.join(CACHE_DIR, "dead_models.json")
LIVE_MODELS_CACHE_FILE = os.path.join(CACHE_DIR, "live_models_cache.json")
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours TTL for live model cache


# ─────────────────────────────────────────────────────────────────
# DEAD MODEL BLACKLIST MANAGER
# ─────────────────────────────────────────────────────────────────

class DeadModelManager:
    """Manages permanently blacklisted / dead models that gave 404 or decommission errors."""

    def __init__(self, file_path: str = DEAD_MODELS_FILE):
        self.file_path = file_path
        self._dead_models: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.file_path):
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._dead_models, f, indent=2)
        except Exception:
            pass

    def is_dead(self, provider: str, model_id: str) -> bool:
        if not provider or not model_id:
            return False
        key = f"{provider.lower()}:{model_id}"
        return key in self._dead_models

    def evict(self, provider: str, model_id: str, reason: str = "") -> bool:
        """
        Permanently blacklist a model that failed with 404 / ModelUnavailable.
        Evicts from runtime memory and saves to disk cache.
        """
        if not provider or not model_id:
            return False

        key = f"{provider.lower()}:{model_id}"
        self._dead_models[key] = {
            "provider": provider.lower(),
            "model": model_id,
            "evicted_at": time.time(),
            "reason": reason or "HTTP 404 Model Not Found / Decommissioned"
        }
        self._save()

        # Evict from runtime provider catalog if present
        try:
            import provider_manager
            cat = provider_manager.PROVIDER_CATALOG.get(provider.lower(), {})
            models = cat.get("models", [])
            cat["models"] = [m for m in models if m.get("id") != model_id]

            # If the evicted model was the user's saved active model, reset to default
            cfg = provider_manager.load_config()
            active_models = cfg.get("active_models", {})
            if active_models.get(provider.lower()) == model_id:
                active_models[provider.lower()] = cat.get("default_model", "")
                provider_manager.save_config(cfg)
        except Exception:
            pass

        return True

    def get_all_dead(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._dead_models)

    def clear(self) -> None:
        self._dead_models.clear()
        self._save()


# ─────────────────────────────────────────────────────────────────
# LIVE MODEL DISCOVERY
# ─────────────────────────────────────────────────────────────────

class LiveModelDiscovery:
    """Discovers genuinely active models from provider APIs."""

    def __init__(self, cache_file: str = LIVE_MODELS_CACHE_FILE, dead_mgr: Optional[DeadModelManager] = None):
        self.cache_file = cache_file
        self.dead_mgr = dead_mgr or get_dead_model_manager()
        self._cache: Dict[str, Dict[str, Any]] = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.cache_file):
            return {}
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)
        except Exception:
            pass

    def get_models(self, provider: str, force_refresh: bool = False) -> List[Dict[str, str]]:
        """
        Returns list of models for provider [{"id": str, "desc": str}].
        Uses cached live models if fresh, else queries the provider API.
        Filters out any dead/blacklisted models.
        """
        prov = provider.lower()
        now = time.time()

        if not force_refresh and prov in self._cache:
            entry = self._cache[prov]
            if now - entry.get("timestamp", 0) < CACHE_TTL_SECONDS:
                models = entry.get("models", [])
                return [m for m in models if not self.dead_mgr.is_dead(prov, m.get("id", ""))]

        # Fetch fresh from provider
        discovered = self._fetch_from_provider(prov)
        if discovered:
            self._cache[prov] = {
                "timestamp": now,
                "models": discovered
            }
            self._save_cache()
            return [m for m in discovered if not self.dead_mgr.is_dead(prov, m.get("id", ""))]

        # If fetch fails or not supported, return cached if available, else static catalog
        if prov in self._cache:
            return [m for m in self._cache[prov].get("models", []) if not self.dead_mgr.is_dead(prov, m.get("id", ""))]

        import provider_manager
        static_models = provider_manager.PROVIDER_CATALOG.get(prov, {}).get("models", [])
        return [m for m in static_models if not self.dead_mgr.is_dead(prov, m.get("id", ""))]

    def _fetch_from_provider(self, provider: str) -> List[Dict[str, str]]:
        """Query live endpoint based on provider."""
        import provider_manager

        api_key = provider_manager.get_api_key(provider)
        cat = provider_manager.PROVIDER_CATALOG.get(provider, {})

        if provider == "openrouter":
            return self._fetch_openrouter_free()
        elif provider == "groq":
            return self._fetch_openai_compatible_models(
                endpoint="https://api.groq.com/openai/v1/models",
                api_key=api_key,
                provider="groq"
            )
        elif provider == "mistral":
            return self._fetch_openai_compatible_models(
                endpoint="https://api.mistral.ai/v1/models",
                api_key=api_key,
                provider="mistral"
            )
        elif provider == "custom":
            cfg = provider_manager.load_config()
            base_url = cfg.get("custom_base_url", "http://localhost:11434/v1")
            return self._fetch_ollama_models(base_url)

        return []

    def _fetch_openrouter_free(self) -> List[Dict[str, str]]:
        """Fetch active free models from OpenRouter API."""
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/models",
                headers={"User-Agent": "KlyroCLI/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            
            models = []
            for item in data.get("data", []):
                model_id = item.get("id", "")
                if not model_id.endswith(":free"):
                    continue
                pricing = item.get("pricing", {})
                if float(pricing.get("prompt", 0) or 0) > 0 or float(pricing.get("completion", 0) or 0) > 0:
                    continue
                ctx = item.get("context_length", 0) or 0
                name = item.get("name", model_id)
                models.append({
                    "id": model_id,
                    "desc": f"🆓 {name} • {ctx // 1000}K ctx"
                })
            return models
        except Exception:
            return []

    def _fetch_openai_compatible_models(self, endpoint: str, api_key: str, provider: str) -> List[Dict[str, str]]:
        """Generic fetcher for OpenAI-compatible /v1/models endpoints."""
        if not api_key:
            return []
        try:
            req = urllib.request.Request(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "KlyroCLI/1.0"
                }
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            models = []
            raw_list = data.get("data", [])
            for item in raw_list:
                m_id = item.get("id", "")
                if not m_id:
                    continue
                # Skip whisper / moderation / embedding models
                m_id_lower = m_id.lower()
                if any(skip in m_id_lower for skip in ["whisper", "tts", "embed", "moderation", "guard"]):
                    continue
                models.append({
                    "id": m_id,
                    "desc": f"⚡ {m_id} • Active on {provider.upper()}"
                })
            # Sort with coding/reasoning models first
            return sorted(models, key=lambda x: x["id"])
        except Exception:
            return []

    def _fetch_ollama_models(self, base_url: str) -> List[Dict[str, str]]:
        """Fetch locally installed models from Ollama /api/tags."""
        # Clean base_url to root (e.g. http://localhost:11434/v1 -> http://localhost:11434)
        clean_url = base_url.rstrip("/").removesuffix("/v1")
        tags_endpoint = f"{clean_url}/api/tags"
        try:
            req = urllib.request.Request(tags_endpoint, headers={"User-Agent": "KlyroCLI/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            models = []
            for item in data.get("models", []):
                name = item.get("name", "")
                if not name:
                    continue
                size_gb = round(item.get("size", 0) / (1024**3), 1)
                models.append({
                    "id": name,
                    "desc": f"💻 Local • {name} ({size_gb} GB)"
                })
            return models
        except Exception:
            return []


# Global instances
_GLOBAL_DEAD_MGR: Optional[DeadModelManager] = None
_GLOBAL_DISCOVERY: Optional[LiveModelDiscovery] = None


def get_dead_model_manager() -> DeadModelManager:
    global _GLOBAL_DEAD_MGR
    if _GLOBAL_DEAD_MGR is None:
        _GLOBAL_DEAD_MGR = DeadModelManager()
    return _GLOBAL_DEAD_MGR


def get_live_discovery() -> LiveModelDiscovery:
    global _GLOBAL_DISCOVERY
    if _GLOBAL_DISCOVERY is None:
        _GLOBAL_DISCOVERY = LiveModelDiscovery()
    return _GLOBAL_DISCOVERY
