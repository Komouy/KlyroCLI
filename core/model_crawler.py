"""
core/model_crawler.py — Klyro Autonomous Official Documentation Model Synchronizer

Explores official provider documentation websites & API endpoints to harvest,
verify, and synchronize active, genuine model identifiers into Klyro's catalog.
Ensures KlyroCLI always stays in sync with what providers officially offer.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any, Callable

import provider_manager
from core.model_discovery import get_dead_model_manager

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".klyro")
OFFICIAL_CATALOG_FILE = os.path.join(CACHE_DIR, "official_models_catalog.json")

# Verified official documentation sources
OFFICIAL_SOURCES = {
    "gemini": {
        "name": "Google Gemini",
        "doc_url": "https://ai.google.dev/gemini-api/docs/models",
        "api_endpoint": "https://generativelanguage.googleapis.com/v1beta/models",
        "is_free_tier_available": True,
    },
    "groq": {
        "name": "Groq LPU",
        "doc_url": "https://console.groq.com/docs/models",
        "api_endpoint": "https://api.groq.com/openai/v1/models",
        "is_free_tier_available": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "doc_url": "https://api-docs.deepseek.com",
        "api_endpoint": "https://api.deepseek.com/models",
        "is_free_tier_available": False,
    },
    "openrouter": {
        "name": "OpenRouter",
        "doc_url": "https://openrouter.ai/models?max_price=0",
        "api_endpoint": "https://openrouter.ai/api/v1/models",
        "is_free_tier_available": True,
    },
    "claude": {
        "name": "Anthropic Claude",
        "doc_url": "https://docs.anthropic.com/en/docs/about-claude/models",
        "api_endpoint": "https://api.anthropic.com/v1/models",
        "is_free_tier_available": False,
    },
    "openai": {
        "name": "OpenAI",
        "doc_url": "https://platform.openai.com/docs/models",
        "api_endpoint": "https://api.openai.com/v1/models",
        "is_free_tier_available": False,
    },
    "custom": {
        "name": "Ollama Local",
        "doc_url": "https://ollama.com/library",
        "api_endpoint": "http://localhost:11434/api/tags",
        "is_free_tier_available": True,
    }
}


def _strip_html_to_text(html: str) -> str:
    """Extract clean text content from HTML, removing scripts and styles."""
    if not html:
        return ""
    # Strip script and style blocks
    cleaned = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Strip HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Collapse multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:12_000]  # Cap to prevent excessive token consumption


class OfficialModelCrawler:
    """Crawls official provider docs and APIs to synchronize genuine models."""

    def __init__(self, catalog_file: str = OFFICIAL_CATALOG_FILE):
        self.catalog_file = catalog_file
        self._dead_mgr = None
        self._catalog: Dict[str, Any] = self._load_catalog()

    @property
    def dead_mgr(self):
        if self._dead_mgr is not None:
            return self._dead_mgr
        return get_dead_model_manager()

    @dead_mgr.setter
    def dead_mgr(self, val):
        self._dead_mgr = val

    def _load_catalog(self) -> Dict[str, Any]:
        if not os.path.exists(self.catalog_file):
            return {}
        try:
            with open(self.catalog_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_catalog(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.catalog_file), exist_ok=True)
            with open(self.catalog_file, "w", encoding="utf-8") as f:
                json.dump(self._catalog, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_synced_models(self, provider: str) -> List[Dict[str, str]]:
        """Return active models for provider from synced official catalog."""
        prov = provider.lower()
        entry = self._catalog.get(prov, {})
        models = entry.get("models", [])
        return [m for m in models if not self.dead_mgr.is_dead(prov, m.get("id", ""))]

    def sync_provider(
        self,
        provider: str,
        ai_assistant: Any = None,
        timeout: int = 8
    ) -> Dict[str, Any]:
        """
        Synchronizes models for a single provider.
        Tries official API endpoint first; falls back to crawling docs.
        """
        prov = provider.lower()
        if prov not in OFFICIAL_SOURCES:
            return {"success": False, "error": f"Unknown provider '{provider}'"}

        src = OFFICIAL_SOURCES[prov]
        api_key = provider_manager.get_api_key(prov)
        models: List[Dict[str, str]] = []

        # 1. Probe official API endpoints where possible
        if prov == "openrouter":
            models = self._fetch_openrouter_models(timeout)
        elif prov == "groq" and api_key:
            models = self._fetch_openai_compatible_endpoint(
                endpoint=src["api_endpoint"],
                api_key=api_key,
                provider_tag="Groq",
                timeout=timeout
            )
        elif prov == "gemini" and api_key:
            models = self._fetch_gemini_endpoint(api_key, timeout)
        elif prov == "deepseek" and api_key:
            models = self._fetch_openai_compatible_endpoint(
                endpoint=src["api_endpoint"],
                api_key=api_key,
                provider_tag="DeepSeek",
                timeout=timeout
            )
        elif prov == "claude" and api_key:
            models = self._fetch_claude_endpoint(api_key, timeout)
        elif prov == "custom":
            cfg = provider_manager.load_config()
            base = cfg.get("custom_base_url", "http://localhost:11434/v1")
            models = self._fetch_ollama_tags(base, timeout)

        # 2. If API was unavailable or had no key, fetch public web documentation
        if not models:
            models = self._crawl_public_docs(prov, src["doc_url"], ai_assistant, timeout)

        if not models:
            # Fallback to static catalog as safety baseline
            static_models = provider_manager.PROVIDER_CATALOG.get(prov, {}).get("models", [])
            models = [dict(m) for m in static_models]

        # Filter out dead models
        filtered = [m for m in models if not self.dead_mgr.is_dead(prov, m.get("id", ""))]

        # Save to local catalog
        self._catalog[prov] = {
            "last_synced": time.time(),
            "source_url": src["doc_url"],
            "model_count": len(filtered),
            "models": filtered
        }
        self._save_catalog()

        return {
            "success": True,
            "provider": prov,
            "source": src["doc_url"],
            "count": len(filtered),
            "models": filtered
        }

    def sync_all(
        self,
        ai_assistant: Any = None,
        callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Synchronizes all supported providers.
        callback(prov, status_text) is called for UI progress updates.
        """
        results = {}
        for prov in OFFICIAL_SOURCES:
            if callback:
                callback(prov, f"Scanning {OFFICIAL_SOURCES[prov]['name']} official docs...")
            res = self.sync_provider(prov, ai_assistant=ai_assistant)
            results[prov] = res
            if callback:
                if res.get("success"):
                    callback(prov, f"Found {res.get('count', 0)} active models")
                else:
                    callback(prov, "Using stable baseline catalog")

        return results

    # ── Internal Fetchers ──────────────────────────────────────────────

    def _fetch_openrouter_models(self, timeout: int) -> List[Dict[str, str]]:
        url = "https://openrouter.ai/api/v1/models"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KlyroCLI/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = []
            for item in data.get("data", []):
                m_id = item.get("id", "")
                if not m_id.endswith(":free"):
                    continue
                pricing = item.get("pricing", {})
                if float(pricing.get("prompt", 0) or 0) > 0 or float(pricing.get("completion", 0) or 0) > 0:
                    continue
                ctx = item.get("context_length", 0) or 0
                name = item.get("name", m_id)
                ctx_k = ctx // 1000 if ctx >= 1000 else ctx
                models.append({
                    "id": m_id,
                    "desc": f"⊙ {name} • {ctx_k}K ctx [100% Free]"
                })
            return models
        except Exception:
            return []

    def _fetch_openai_compatible_endpoint(
        self,
        endpoint: str,
        api_key: str,
        provider_tag: str,
        timeout: int
    ) -> List[Dict[str, str]]:
        try:
            req = urllib.request.Request(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "User-Agent": "KlyroCLI/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = []
            for item in data.get("data", []):
                m_id = item.get("id", "")
                if not m_id:
                    continue
                # Exclude whisper/tts/embed
                m_lower = m_id.lower()
                if any(skip in m_lower for skip in ["whisper", "tts", "embed", "moderation", "guard"]):
                    continue
                desc = f"★ {provider_tag} • {m_id}"
                if "versatile" in m_lower or "70b" in m_lower:
                    desc = f"★ Flagship 70B • High-accuracy coding & reasoning"
                elif "instant" in m_lower or "8b" in m_lower:
                    desc = f"⌁ Ultra-fast ~500 tok/s • Low-latency scripting"
                models.append({"id": m_id, "desc": desc})
            return models
        except Exception:
            return []

    def _fetch_gemini_endpoint(self, api_key: str, timeout: int) -> List[Dict[str, str]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KlyroCLI/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = []
            for item in data.get("models", []):
                raw_name = item.get("name", "")
                m_id = raw_name.replace("models/", "")
                methods = item.get("supportedGenerationMethods", [])
                if "generateContent" not in methods:
                    continue
                m_lower = m_id.lower()
                if any(skip in m_lower for skip in ["embedding", "aqa", "imagen", "text-embedding"]):
                    continue
                display = item.get("displayName", m_id)
                input_tokens = item.get("inputTokenLimit", 0) or 0
                ctx_k = input_tokens // 1000 if input_tokens >= 1000 else input_tokens
                ctx_str = f" • {ctx_k}K ctx" if ctx_k else ""
                models.append({
                    "id": m_id,
                    "desc": f"▲ Google • {display}{ctx_str}"
                })
            return models
        except Exception:
            return []

    def _fetch_claude_endpoint(self, api_key: str, timeout: int) -> List[Dict[str, str]]:
        url = "https://api.anthropic.com/v1/models"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "KlyroCLI/1.0"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = []
            for item in data.get("data", []):
                m_id = item.get("id", "")
                if not m_id:
                    continue
                models.append({
                    "id": m_id,
                    "desc": f"★ Anthropic • {item.get('display_name', m_id)}"
                })
            return models
        except Exception:
            return []

    def _fetch_ollama_tags(self, base_url: str, timeout: int) -> List[Dict[str, str]]:
        clean_url = base_url.rstrip("/").removesuffix("/v1")
        tags_endpoint = f"{clean_url}/api/tags"
        try:
            req = urllib.request.Request(tags_endpoint, headers={"User-Agent": "KlyroCLI/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = []
            for item in data.get("models", []):
                m_name = item.get("name", "")
                if not m_name:
                    continue
                size_gb = item.get("size", 0) / (1024 ** 3)
                models.append({
                    "id": m_name,
                    "desc": f"▩ Local Ollama • {size_gb:.1f}GB [Offline]"
                })
            return models
        except Exception:
            return []

    def _crawl_public_docs(
        self,
        provider: str,
        doc_url: str,
        ai_assistant: Any,
        timeout: int
    ) -> List[Dict[str, str]]:
        """
        Fetches official documentation HTML and extracts model IDs using AI assistant
        or regex heuristics.
        """
        try:
            req = urllib.request.Request(
                doc_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KlyroCLI/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_html = resp.read().decode("utf-8", errors="replace")
            doc_text = _strip_html_to_text(raw_html)
        except Exception:
            return []

        # Heuristic regex extraction based on provider patterns
        extracted: List[Dict[str, str]] = []
        if provider == "groq":
            candidates = set(re.findall(r"\b(llama-3\.[1-3]-[0-9]+b-[a-z]+|deepseek-r1-[a-z0-9-]+|qwen-[a-z0-9-]+|openai/gpt-oss-[0-9]+b)\b", doc_text, re.IGNORECASE))
            for cid in sorted(candidates):
                extracted.append({"id": cid.lower(), "desc": f"★ Groq Official Docs • {cid}"})
        elif provider == "gemini":
            candidates = set(re.findall(r"\b(gemini-[1-4]\.[0-9]+-[a-z-]+|gemini-4-[a-z]+)\b", doc_text, re.IGNORECASE))
            for cid in sorted(candidates):
                extracted.append({"id": cid.lower(), "desc": f"▲ Google AI Studio Docs • {cid}"})
        elif provider == "deepseek":
            candidates = set(re.findall(r"\b(deepseek-[a-z0-9-]+)\b", doc_text, re.IGNORECASE))
            for cid in sorted(candidates):
                extracted.append({"id": cid.lower(), "desc": f"◈ DeepSeek Official Docs • {cid}"})

        return extracted


# Global singleton
_crawler_instance: Optional[OfficialModelCrawler] = None


def get_model_crawler() -> OfficialModelCrawler:
    global _crawler_instance
    if _crawler_instance is None:
        _crawler_instance = OfficialModelCrawler()
    return _crawler_instance
