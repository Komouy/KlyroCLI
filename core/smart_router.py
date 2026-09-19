"""
core/smart_router.py — Universal Workload-Based Smart Router & Resilient Fallback

Classifies incoming user queries into 4 workload tiers (LIGHT, CODE, REASONING, HEAVY)
and matches them against all actively configured AI providers (Gemini, Groq, Cerebras,
OpenRouter, Mistral, DeepSeek, Custom/Ollama) to select the optimal model.
Provides automatic fallback cascades when rate limits (429) or quota errors occur.
"""

from __future__ import annotations

import os
import re
from enum import Enum
from typing import Optional, Dict, List, Tuple, Any

import provider_manager


class WorkloadTier(str, Enum):
    LIGHT = "LIGHT"          # Quick questions, terminal commands, short queries (speed priority)
    CODE = "CODE"            # Writing/editing code, debugging, tests, refactoring (coding accuracy)
    REASONING = "REASONING"  # Math, algorithms, architecture, complex root-cause (logic depth)
    HEAVY = "HEAVY"          # Whole-project audit, multi-file migrations, context > 40K chars (long context)


# ─────────────────────────────────────────────────────────────────
# WORKLOAD CLASSIFIER
# ─────────────────────────────────────────────────────────────────

HEAVY_KEYWORDS = [
    "seluruh", "semua file", "keseluruhan", "audit", "arsitektur proyek",
    "full codebase", "migrate", "migrasi", "project wide", "refaktor seluruh",
    "dokumentasi lengkap", "analisis struktur", "analisis proyek", "codebase overview",
    "entire project", "all files", "across the project"
]

REASONING_KEYWORDS = [
    "algoritma", "algorithm", "kompleksitas", "complexity", "big-o",
    "race condition", "deadlock", "concurrency", "matematika", "math", "rumus",
    "desain sistem", "arsitektur sistem", "tradeoff", "trade-off", "deep analysis",
    "analisis mendalam", "kenapa ini terjadi", "mengapa bisa", "root cause",
    "prove", "pembuktian", "formal proof", "logic puzzle", "deduce"
]

CODE_KEYWORDS = [
    "buat file", "create file", "buatkan", "tulis kode", "implementasikan",
    "implement", "tambahkan fitur", "add feature", "refactor", "debug",
    "perbaiki error", "fix bug", "traceback", "syntax error", "unit test",
    "endpoint", "fungsi", "class", "metode", "method", "patch", "diff",
    "tulis script", "write function", "buat class", "handler", "controller"
]


def classify_workload(prompt: str, context_chars: int = 0, file_count: int = 0) -> Tuple[WorkloadTier, str]:
    """
    Analyzes prompt text, word count, and context size to determine workload tier.
    Returns: (WorkloadTier, reason_label)
    """
    if not prompt:
        return WorkloadTier.LIGHT, "Empty query (speed priority)"

    q = prompt.lower()
    n_words = len(q.split())

    # 1. Heavy context check: explicit whole-project request OR large context across project
    if any(kw in q for kw in HEAVY_KEYWORDS):
        return WorkloadTier.HEAVY, "Whole-project analysis / broad audit requested"

    if context_chars > 45_000:
        return WorkloadTier.HEAVY, f"High context workload ({context_chars:,} chars across {file_count} files)"

    # 2. Deep reasoning check
    if any(kw in q for kw in REASONING_KEYWORDS):
        return WorkloadTier.REASONING, "Deep logic / algorithmic reasoning requested"

    # 3. Standard coding check
    if any(kw in q for kw in CODE_KEYWORDS) or n_words > 35:
        return WorkloadTier.CODE, "Code implementation / debugging requested"

    # 4. Light / Fast query
    return WorkloadTier.LIGHT, "Quick query / interaction (ultra-fast speed priority)"


# ─────────────────────────────────────────────────────────────────
# TIER MODEL PREFERENCES PER PROVIDER
# ─────────────────────────────────────────────────────────────────

TIER_PROVIDER_PREFERENCES: Dict[WorkloadTier, List[Dict[str, Any]]] = {
    WorkloadTier.LIGHT: [
        {"provider": "groq",       "model": "openai/gpt-oss-20b",       "label": "Groq LPU (~500 tok/s)"},
        {"provider": "cerebras",   "model": "llama3.1-8b",              "label": "Cerebras Wafer (Ultra Fast)"},
        {"provider": "gemini",     "model": "gemini-3.5-flash-lite",    "label": "Gemini Flash Lite"},
        {"provider": "mistral",    "model": "mistral-small-latest",     "label": "Mistral Small"},
        {"provider": "openrouter", "model": "openrouter/auto",          "label": "OpenRouter Auto Free"},
        {"provider": "deepseek",   "model": "deepseek-v4-flash",        "label": "DeepSeek Flash"},
        {"provider": "custom",     "model": None,                       "label": "Local Ollama"},
    ],
    WorkloadTier.CODE: [
        {"provider": "groq",       "model": "openai/gpt-oss-120b",      "label": "Groq Flagship 120B"},
        {"provider": "mistral",    "model": "codestral-latest",         "label": "Mistral Codestral (Coding Specialist)"},
        {"provider": "openrouter", "model": "z-ai/glm-5.2:free",        "label": "OpenRouter GLM 5.2 Free"},
        {"provider": "deepseek",   "model": "deepseek-chat",            "label": "DeepSeek V3 (Top-tier Coding)"},
        {"provider": "gemini",     "model": "gemini-3.6-flash",         "label": "Gemini 3.6 Flash"},
        {"provider": "cerebras",   "model": "gpt-oss-120b",             "label": "Cerebras 120B"},
        {"provider": "custom",     "model": None,                       "label": "Local Ollama"},
    ],
    WorkloadTier.REASONING: [
        {"provider": "deepseek",   "model": "deepseek-reasoner",        "label": "DeepSeek R1 (Thinking Mode)"},
        {"provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free", "label": "Nemotron 3 Super (Reasoning)"},
        {"provider": "gemini",     "model": "gemini-3.1-pro-preview",   "label": "Gemini 3.1 Pro (Complex Logic)"},
        {"provider": "groq",       "model": "qwen/qwen3.8-27b",         "label": "Groq Qwen 27B Logic"},
        {"provider": "mistral",    "model": "mistral-large-latest",     "label": "Mistral Large"},
        {"provider": "cerebras",   "model": "gpt-oss-120b",             "label": "Cerebras 120B"},
        {"provider": "custom",     "model": None,                       "label": "Local Ollama"},
    ],
    WorkloadTier.HEAVY: [
        {"provider": "gemini",     "model": "gemini-3.6-flash",         "label": "Gemini 3.6 (1M Token Context)"},
        {"provider": "openrouter", "model": "minimax/minimax-m3:free",  "label": "MiniMax M3 Free (1M Context)"},
        {"provider": "deepseek",   "model": "deepseek-chat",            "label": "DeepSeek Chat (64K Context)"},
        {"provider": "mistral",    "model": "mistral-small-latest",     "label": "Mistral Small"},
        {"provider": "groq",       "model": "openai/gpt-oss-120b",      "label": "Groq 120B"},
        {"provider": "cerebras",   "model": "gpt-oss-120b",             "label": "Cerebras 120B"},
        {"provider": "custom",     "model": None,                       "label": "Local Ollama"},
    ],
}


# ─────────────────────────────────────────────────────────────────
# SMART ROUTER
# ─────────────────────────────────────────────────────────────────

class SmartRouter:
    """
    Intelligent dynamic routing engine that profiles workloads, detects active
    providers, and routes requests to the optimal AI model with automatic fallback.
    """

    def __init__(self):
        self.enabled = True
        self._temp_excluded_providers: set[str] = set()

    def get_configured_providers(self) -> Dict[str, str]:
        """
        Returns dict of provider_id -> api_key for all providers that are ready to use.
        Custom provider (Ollama) is considered ready if base_url is configured.
        """
        cfg = provider_manager.load_config()
        configured = {}
        for prov_id in provider_manager.PROVIDER_CATALOG:
            key = provider_manager.get_api_key(prov_id)
            if key:
                configured[prov_id] = key
            elif prov_id == "custom":
                # Ollama doesn't require an API key
                configured[prov_id] = "local"
        return configured

    def route(
        self,
        prompt: str,
        context_chars: int = 0,
        file_count: int = 0,
        exclude_providers: Optional[List[str]] = None,
        manual_override: Optional[str] = None,
    ) -> Tuple[str, str, str, WorkloadTier]:
        """
        Determines the best provider and model for a given prompt and context.
        Returns:
            (provider_id: str, model_id: str, route_explanation: str, tier: WorkloadTier)
        """
        tier, tier_reason = classify_workload(prompt, context_chars, file_count)
        configured = self.get_configured_providers()

        # If user has a manual override / locked provider and it's configured
        if manual_override and manual_override in configured:
            active_cat = provider_manager.PROVIDER_CATALOG.get(manual_override, {})
            model = provider_manager.load_config().get("active_models", {}).get(manual_override, active_cat.get("default_model", ""))
            return manual_override, model, f"Manual Override ({active_cat.get('name', manual_override)})", tier

        excludes = set(exclude_providers or []) | self._temp_excluded_providers
        try:
            from core.model_discovery import get_dead_model_manager
            dead_mgr = get_dead_model_manager()
        except Exception:
            dead_mgr = None

        # Search the preferences for this tier
        candidates = TIER_PROVIDER_PREFERENCES.get(tier, [])
        for pref in candidates:
            prov = pref["provider"]
            if prov in configured and prov not in excludes:
                # If context is large (>35k chars), avoid tight-TPM providers (groq, cerebras)
                # if a large-context provider is also configured and ready
                if context_chars > 35_000 and prov in ("groq", "cerebras"):
                    has_large_cap = any(
                        p in configured and p not in excludes
                        for p in ("gemini", "openrouter", "deepseek", "mistral")
                    )
                    if has_large_cap:
                        continue

                cat = provider_manager.PROVIDER_CATALOG.get(prov, {})
                model = pref["model"] or cat.get("default_model", "")
                if dead_mgr and dead_mgr.is_dead(prov, model):
                    continue
                label = pref["label"]
                reason = f"[{tier.value} • {label}] {tier_reason}"
                return prov, model, reason, tier

        # Fallback: if no candidates in tier, take ANY available configured provider not excluded
        for prov in configured:
            if prov not in excludes:
                cat = provider_manager.PROVIDER_CATALOG.get(prov, {})
                model = cat.get("default_model", "")
                if dead_mgr and dead_mgr.is_dead(prov, model):
                    continue
                return prov, model, f"[Fallback Provider] {cat.get('name', prov)}", tier

        # Ultimate fallback: return whatever is configured or the default active provider
        active_prov, active_model, _, _ = provider_manager.get_active_provider()
        return active_prov, active_model, "Default Provider (No other alternatives ready)", tier

    def get_fallback_candidates(
        self,
        tier: WorkloadTier,
        failed_provider: str,
        additional_excludes: Optional[List[str]] = None
    ) -> List[Tuple[str, str, str]]:
        """
        Returns a list of viable fallback (provider, model, label) alternatives for a given tier.
        """
        configured = self.get_configured_providers()
        excludes = {failed_provider} | set(additional_excludes or []) | self._temp_excluded_providers
        try:
            from core.model_discovery import get_dead_model_manager
            dead_mgr = get_dead_model_manager()
        except Exception:
            dead_mgr = None

        candidates = []
        # First try other providers in the same tier
        for pref in TIER_PROVIDER_PREFERENCES.get(tier, []):
            prov = pref["provider"]
            if prov in configured and prov not in excludes:
                cat = provider_manager.PROVIDER_CATALOG.get(prov, {})
                model = pref["model"] or cat.get("default_model", "")
                if dead_mgr and dead_mgr.is_dead(prov, model):
                    continue
                candidates.append((prov, model, pref["label"]))
                excludes.add(prov)

        # Next try any remaining configured provider
        for prov in configured:
            if prov not in excludes:
                cat = provider_manager.PROVIDER_CATALOG.get(prov, {})
                model = cat.get("default_model", "")
                if dead_mgr and dead_mgr.is_dead(prov, model):
                    continue
                candidates.append((prov, model, cat.get("name", prov)))
                excludes.add(prov)

        return candidates

    def temp_exclude_provider(self, provider_id: str) -> None:
        """Temporarily mark a provider as unavailable (e.g. Rate Limit / 429)."""
        self._temp_excluded_providers.add(provider_id)

    def reset_exclusions(self) -> None:
        """Reset temporary provider exclusions."""
        self._temp_excluded_providers.clear()


# Global singleton instance
_GLOBAL_ROUTER: Optional[SmartRouter] = None


def get_smart_router() -> SmartRouter:
    global _GLOBAL_ROUTER
    if _GLOBAL_ROUTER is None:
        _GLOBAL_ROUTER = SmartRouter()
    return _GLOBAL_ROUTER
