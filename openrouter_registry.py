"""
openrouter_registry.py — Klyro Dynamic Model Registry for OpenRouter
Fetches live model metadata from OpenRouter Models API, builds a local
capability-scored registry, and provides a Smart Router that matches
task profiles to the best available free model.

Architecture (per Klyro research doc):
  OpenRouter Models API
    → filter free / price
    → filter context
    → filter tools / structured output
    → filter coding / agentic benchmark
    → cek status / availability
    → health test
    → Klyro Model Registry
    → Smart Router (task profile × model capability = best match)
"""

import json
import time
import urllib.request
import urllib.error
import os
import re
from typing import Optional

# ─────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────
OPENROUTER_MODELS_URL  = "https://openrouter.ai/api/v1/models"
REGISTRY_CACHE_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".klyro", "model_registry.json")
REGISTRY_TTL_SECONDS   = 6 * 3600   # Refresh cache every 6 hours
REQUEST_TIMEOUT        = 12         # seconds

# Models pinned from research doc — always included even if API is unreachable
PINNED_FREE_MODELS = [
    {
        "id":          "z-ai/glm-5.2:free",
        "name":        "GLM 5.2",
        "context":     256_000,
        "is_free":     True,
        "tools":       True,
        "structured":  True,
        "capability":  {
            "coding":     10,
            "reasoning":  9,
            "context":    9,
            "tool_use":   10,
            "speed":      6,
        },
        "role":        "complex_coding",
        "desc":        "🧠 GLM 5.2 Free • Complex Coding, Agent, Long-horizon Engineering",
        "pinned":      True,
    },
    {
        "id":          "minimax/minimax-m3:free",
        "name":        "MiniMax M3",
        "context":     1_000_000,
        "is_free":     True,
        "tools":       True,
        "structured":  True,
        "capability":  {
            "coding":     8,
            "reasoning":  8,
            "context":    10,
            "tool_use":   9,
            "speed":      7,
        },
        "role":        "long_context_agent",
        "desc":        "🌊 MiniMax M3 Free • 1M Context, Multimodal, Long-horizon Agent",
        "pinned":      True,
    },
    {
        "id":          "nvidia/nemotron-3-super-120b-a12b:free",
        "name":        "Nemotron 3 Super 120B",
        "context":     262_144,
        "is_free":     True,
        "tools":       True,
        "structured":  True,
        "capability":  {
            "coding":     9,
            "reasoning":  10,
            "context":    9,
            "tool_use":   8,
            "speed":      4,
        },
        "role":        "heavy_reasoning",
        "desc":        "🔥 Nemotron 3 Super Free • 120B, Multi-agent Reasoning",
        "pinned":      True,
    },
    {
        "id":          "openrouter/auto",
        "name":        "OpenRouter Auto (Free)",
        "context":     128_000,
        "is_free":     True,
        "tools":       True,
        "structured":  True,
        "capability":  {
            "coding":     6,
            "reasoning":  6,
            "context":    6,
            "tool_use":   6,
            "speed":      9,
        },
        "role":        "fallback",
        "desc":        "🔄 OpenRouter Auto • Random best free model (simple fallback)",
        "pinned":      True,
    },
]

# ─────────────────────────────────────────────────────────────────
# TASK PROFILE
# ─────────────────────────────────────────────────────────────────
class TaskProfile:
    """Scores a user prompt across capability dimensions (0–10)."""

    HEAVY_CODING_KW = [
        "refactor", "refaktor", "architecture", "arsitektur", "rewrite", "restruktur",
        "migrate", "migrate", "generate project", "full stack", "generate all",
        "implementasikan seluruh", "buat seluruh", "audit kode", "code review",
        "analisis kode", "review kode", "dokumentasi lengkap", "buat aplikasi",
        "create application", "scaffold",
    ]
    MEDIUM_CODING_KW = [
        "buat file", "create file", "buatkan", "tambahkan", "implement",
        "debug", "error", "traceback", "optimasi", "perbaiki", "fix",
        "tambah fitur", "add feature", "endpoint", "fungsi", "function",
        "class", "unit test", "test case", "refactor fungsi",
    ]
    REASONING_KW = [
        "jelaskan", "explain", "kenapa", "why", "bagaimana cara", "how to",
        "perbandingan", "compare", "analisa", "analyze", "pilihan terbaik",
        "best practice", "trade-off", "strategi", "plan", "desain",
    ]
    LONG_CONTEXT_KW = [
        "seluruh", "semua file", "keseluruhan", "semua kode", "seluruh proyek",
        "all files", "entire codebase", "whole project",
    ]

    def __init__(self, prompt: str, context_chars: int = 0, file_count: int = 0):
        self.prompt        = prompt
        self.context_chars = context_chars
        self.file_count    = file_count
        self._scores       = None

    def scores(self) -> dict:
        if self._scores is not None:
            return self._scores

        q         = self.prompt.lower()
        n_words   = len(q.split())
        ctx_chars = self.context_chars

        # ── Coding score ──────────────────────────────────────────
        coding = 3  # baseline
        if any(kw in q for kw in self.HEAVY_CODING_KW):
            coding = 10
        elif any(kw in q for kw in self.MEDIUM_CODING_KW):
            coding = 7
        elif n_words > 20:
            coding = 5

        # ── Reasoning score ───────────────────────────────────────
        reasoning = 3
        if any(kw in q for kw in self.REASONING_KW):
            reasoning = 8
        if coding >= 9:
            reasoning = max(reasoning, 8)

        # ── Context score ───────────────────────────────────────────
        # Workspace size alone must NOT decide this — a short "hi" in a
        # 500K-char project must not score as HIGH just because the
        # workspace happens to be big. Context score should reflect
        # whether the CURRENT MESSAGE actually needs the project context
        # (explicit "seluruh/all files" keywords, or a substantial query
        # that plausibly references code), with workspace size only
        # acting as a secondary multiplier/cap once that's established.
        needs_context = any(kw in q for kw in self.LONG_CONTEXT_KW) or n_words > 12 or coding >= 7

        if not needs_context:
            # Short, contextless messages ("hi", "terima kasih", "ok")
            # never score high on context, regardless of workspace size.
            context = 3
        elif any(kw in q for kw in self.LONG_CONTEXT_KW):
            context = 10
        elif ctx_chars > 100_000:
            context = 10
        elif ctx_chars > 40_000 or self.file_count > 8:
            context = 7
        elif ctx_chars > 10_000:
            context = 5
        else:
            context = 3

        # ── Tool use score ────────────────────────────────────────
        tool_use = 5
        action_kw = [
            "buat file", "create file", "delete", "rename", "run", "execute",
            "jalankan", "install", "git commit", "buat folder", "mkdir",
        ]
        if any(kw in q for kw in action_kw) or coding >= 9:
            tool_use = 9

        # ── Speed priority (inverse of complexity) ────────────────
        speed = max(1, 10 - max(coding, reasoning))

        self._scores = {
            "coding":    coding,
            "reasoning": reasoning,
            "context":   context,
            "tool_use":  tool_use,
            "speed":     speed,
        }
        return self._scores

    def complexity_label(self) -> str:
        s = self.scores()
        peak = max(s["coding"], s["reasoning"], s["context"])
        if peak >= 9:
            return "HIGH"
        if peak >= 6:
            return "MEDIUM"
        return "LOW"


# ─────────────────────────────────────────────────────────────────
# REGISTRY CACHE HELPERS
# ─────────────────────────────────────────────────────────────────
def _load_cache() -> Optional[dict]:
    """Load registry cache from disk if fresh."""
    if not os.path.exists(REGISTRY_CACHE_FILE):
        return None
    try:
        with open(REGISTRY_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        age = time.time() - data.get("fetched_at", 0)
        if age > REGISTRY_TTL_SECONDS:
            return None
        return data
    except Exception:
        return None


def _save_cache(registry: list):
    """Persist registry to disk cache."""
    os.makedirs(os.path.dirname(REGISTRY_CACHE_FILE), exist_ok=True)
    try:
        with open(REGISTRY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": time.time(), "models": registry}, f, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────
# OPENROUTER API FETCH
# ─────────────────────────────────────────────────────────────────
def _score_from_api_metadata(m: dict) -> dict:
    """Derive capability scores from OpenRouter model metadata."""
    model_id   = m.get("id", "").lower()
    name       = m.get("name", "").lower()
    ctx        = m.get("context_length", 0) or 0

    coding    = 5
    reasoning = 5
    speed     = 5
    tool_use  = 5

    # Context tier
    context = 3
    if ctx >= 500_000:
        context = 10
    elif ctx >= 100_000:
        context = 8
    elif ctx >= 50_000:
        context = 6
    elif ctx >= 16_000:
        context = 4

    # Model-name heuristics
    size_match = re.search(r"(\d+)b", model_id + name)
    if size_match:
        params = int(size_match.group(1))
        if params >= 100:
            coding    = 9
            reasoning = 9
            speed     = 3
        elif params >= 30:
            coding    = 7
            reasoning = 7
            speed     = 5
        elif params >= 7:
            coding    = 5
            reasoning = 5
            speed     = 8

    # Known strong model families
    if any(s in model_id for s in ["glm", "qwen", "deepseek", "nemotron", "gpt"]):
        coding    = max(coding, 8)
        reasoning = max(reasoning, 8)
    if any(s in model_id for s in ["minimax", "claude", "gemini"]):
        coding    = max(coding, 7)
        context   = max(context, 8)
    if "mini" in model_id or "small" in model_id or "lite" in model_id:
        speed  = max(speed, 8)
        coding = min(coding, 7)

    # Tool use — based on API-reported supported_parameters
    supported = m.get("supported_parameters", []) or []
    if "tools" in supported or "tool_choice" in supported:
        tool_use = 8

    return {
        "coding":    coding,
        "reasoning": reasoning,
        "context":   context,
        "tool_use":  tool_use,
        "speed":     speed,
    }


def _assign_role(cap: dict, context_length: int) -> str:
    """Assign a routing role based on capability profile."""
    if cap["coding"] >= 9 and cap["tool_use"] >= 8:
        return "complex_coding"
    if context_length >= 500_000:
        return "long_context_agent"
    if cap["reasoning"] >= 9:
        return "heavy_reasoning"
    if cap["speed"] >= 8:
        return "fast_light"
    return "general"


def fetch_free_models(api_key: str = "") -> list:
    """
    Fetch model list from OpenRouter Models API and return filtered,
    scored list of free models. Falls back to PINNED_FREE_MODELS on error.
    """
    headers = {
        "Content-Type":  "application/json",
        "User-Agent":    "KlyroCLI/2.5",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        req  = urllib.request.Request(OPENROUTER_MODELS_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []

    discovered = []
    for m in raw.get("data", []):
        model_id = m.get("id", "")
        if not model_id.endswith(":free"):
            continue

        pricing = m.get("pricing", {})
        prompt_price  = float(pricing.get("prompt",     0) or 0)
        completion_price = float(pricing.get("completion", 0) or 0)
        if prompt_price > 0 or completion_price > 0:
            continue  # truly free only

        ctx      = m.get("context_length", 0) or 0
        name     = m.get("name", model_id)
        cap      = _score_from_api_metadata(m)
        role     = _assign_role(cap, ctx)
        supported = m.get("supported_parameters", []) or []

        discovered.append({
            "id":         model_id,
            "name":       name,
            "context":    ctx,
            "is_free":    True,
            "tools":      ("tools" in supported or "tool_choice" in supported),
            "structured": ("structured_outputs" in supported or "response_format" in supported),
            "capability": cap,
            "role":       role,
            "desc":       f"🆓 {name} • {ctx // 1000}K ctx • {role}",
            "pinned":     False,
        })

    return discovered


# ─────────────────────────────────────────────────────────────────
# MODEL REGISTRY
# ─────────────────────────────────────────────────────────────────
class OpenRouterRegistry:
    """
    Maintains a local Model Registry of free OpenRouter models.
    Merges pinned models with dynamically discovered ones.
    Provides capability-scored Smart Routing.
    """

    def __init__(self):
        self._registry: list = []
        self._loaded          = False
        self._blacklisted_ids: set = set()
        # Populated during load() when pinned models are detected as stale.
        # Callers should check this after load() and surface warnings to the user.
        self._stale_pinned_warnings: list = []

    def get_stale_pinned_warnings(self) -> list:
        """Return and clear any stale-pinned-model warnings accumulated during load()."""
        warnings = list(self._stale_pinned_warnings)
        self._stale_pinned_warnings.clear()
        return warnings

    # ── Loading ───────────────────────────────────────────────────

    def load(self, api_key: str = "", force_refresh: bool = False):
        """Load registry from cache or fetch from API."""
        if force_refresh:
            self._blacklisted_ids.clear()

        if not force_refresh:
            cached = _load_cache()
            if cached:
                self._registry = self._merge(cached.get("models", []))
                self._loaded   = True
                return

        discovered = fetch_free_models(api_key)
        if discovered:
            _save_cache(discovered)
            # ── Proactive stale pinned model check ────────────────
            # If the live API response came back successfully, compare
            # pinned model IDs against it. Any pinned model that is no
            # longer present in the API is evicted *now* (before the
            # next routing call fails with a 404 mid-stream).
            live_ids = {m.get("id") for m in discovered if m.get("id")}
            for pinned in PINNED_FREE_MODELS:
                pid = pinned.get("id", "")
                if pid and pid not in live_ids:
                    self._blacklisted_ids.add(pid)
                    self._stale_pinned_warnings.append(
                        f"⚠️  Model pinned '{pinned.get('name', pid)}' ({pid}) "
                        f"sudah tidak tersedia di OpenRouter API dan telah dinonaktifkan secara otomatis."
                    )

        self._registry = self._merge(discovered)
        self._loaded   = True

    def evict_model(self, model_id: str, reason: str = "") -> bool:
        """
        Evicts a dead/deleted model from memory and disk cache.
        Adds it to _blacklisted_ids so it won't be re-added or routed to.
        """
        if not model_id:
            return False
        self._blacklisted_ids.add(model_id)
        original_len = len(self._registry)
        self._registry = [m for m in self._registry if m.get("id") != model_id]
        evicted = len(self._registry) < original_len

        # Prune from disk cache so deleted model isn't reloaded
        try:
            cached = _load_cache()
            if cached and "models" in cached:
                cached_models = [m for m in cached["models"] if m.get("id") != model_id]
                _save_cache(cached_models)
            elif evicted:
                _save_cache([m for m in self._registry if not m.get("pinned")])
        except Exception:
            pass

        return evicted

    def _merge(self, discovered: list) -> list:
        """
        Merge pinned + discovered, deduplicating by id.
        Pinned models provide baseline metadata.
        Models in self._blacklisted_ids are strictly excluded.
        """
        merged = {m["id"]: m for m in PINNED_FREE_MODELS if m.get("id") not in self._blacklisted_ids}
        for m in discovered:
            m_id = m.get("id")
            if m_id and m_id not in self._blacklisted_ids:
                if m_id not in merged:
                    merged[m_id] = m
                else:
                    live_data = dict(m)
                    live_data.update(merged[m_id])
                    merged[m_id] = live_data
        return list(merged.values())

    def ensure_loaded(self, api_key: str = ""):
        if not self._loaded:
            self.load(api_key)

    # ── Registry queries ──────────────────────────────────────────
    def all_models(self) -> list:
        return [m for m in self._registry if m.get("id") not in self._blacklisted_ids]

    def get_model(self, model_id: str) -> Optional[dict]:
        if model_id in self._blacklisted_ids:
            return None
        for m in self._registry:
            if m["id"] == model_id:
                return m
        return None

    def models_for_dropdown(self) -> list:
        """Return list of {id, desc} dicts for provider_manager dropdown UI."""
        result = []
        for m in self.all_models():
            result.append({"id": m["id"], "desc": m.get("desc", m["name"])})
        return result

    # ── Smart Router ──────────────────────────────────────────────
    def route(
        self,
        task: TaskProfile,
        exclude_ids: list = None,
        require_tools: bool = False,
    ) -> Optional[dict]:
        """
        Score every registered model against the task profile and return
        the best match, excluding any model ids in exclude_ids.

        Scoring formula:
          score = Σ(dim_weight × min(task_need, model_capability)) / max_possible
        """
        exclude = set(exclude_ids or []) | self._blacklisted_ids
        candidates = [
            m for m in self._registry
            if m["id"] not in exclude
            and m.get("is_free", False)
            and (not require_tools or m.get("tools", False))
            and m["id"] != "openrouter/auto"   # reserve auto as last resort
        ]

        if not candidates:
            # Last resort: return openrouter/auto
            return self.get_model("openrouter/auto")

        task_scores = task.scores()

        # Dimension weights — tune these for Klyro's coding-first focus
        WEIGHTS = {
            "coding":    3.0,
            "reasoning": 2.0,
            "context":   2.0,
            "tool_use":  2.0,
            "speed":     1.0,
        }
        max_possible = sum(10 * w for w in WEIGHTS.values())

        best_model = None
        best_score = -1.0

        for m in candidates:
            cap   = m.get("capability", {})
            score = 0.0
            for dim, weight in WEIGHTS.items():
                need    = task_scores.get(dim, 5)
                ability = cap.get(dim, 5)
                # Reward matching capability to need; penalise overkill less than shortfall
                match   = min(need, ability)
                score  += weight * match
            norm = score / max_possible

            # Bonus: pinned/researched models get a small trust bump
            if m.get("pinned"):
                norm += 0.05

            if norm > best_score:
                best_score = norm
                best_model = m

        return best_model

    def route_label(self, model: dict, task: TaskProfile) -> str:
        """Human-readable routing reason for the Klyro UI."""
        complexity = task.complexity_label()
        role       = model.get("role", "general")
        name       = model.get("name", model["id"])
        return f"OpenRouter Smart Route ({complexity} → {name} [{role}])"

    # ── Quality Checker ───────────────────────────────────────────
    def quality_score(self, response: str, prompt: str) -> tuple[int, str]:
        """
        Returns (score 0–100, reason) evaluating response quality.
        score < 60 → trigger reroute to stronger candidate.

        Checks:
          1. Length adequacy
          2. Code block presence for coding requests
          3. Named code fence (```:lang:filename) for file requests
          4. Refusal / AI-cop-out phrases
          5. Truncation detection
        """
        if not response or len(response.strip()) < 15:
            return 0, "Respons kosong atau terlalu pendek"

        score  = 100
        reason = "OK"
        q      = prompt.lower()

        # ── 1. Length adequacy ────────────────────────────────────
        if len(response.strip()) < 80:
            score  -= 30
            reason  = "Respons terlalu pendek"

        # ── 2. Code block for coding requests ────────────────────
        coding_kw = [
            "buat file", "create file", "buatkan", "implement", "code",
            "function", "fungsi", "class", "endpoint", "refactor",
        ]
        if any(kw in q for kw in coding_kw):
            if "```" not in response:
                score  -= 35
                reason  = "Tidak ada code block untuk permintaan coding"
            elif not re.search(r"```\w+:[^\n]+", response):
                # Named fence missing — partial penalty
                score  -= 15
                reason  = "Code block tanpa nama file"

        # ── 3. Refusal / cop-out phrases ──────────────────────────
        refusal = [
            "i'm sorry", "i cannot", "i'm unable", "as an ai",
            "i don't have the ability", "i'm not able to",
            "maaf, saya tidak bisa", "saya tidak dapat",
        ]
        r = response.lower()
        if any(p in r for p in refusal) and len(response) < 400:
            score  -= 50
            reason  = "Model menolak atau tidak mampu memenuhi permintaan"

        # ── 4. Truncation detection ───────────────────────────────
        truncation_signals = ["...[truncated", "...continues", "[output cut"]
        if any(s in response.lower() for s in truncation_signals):
            score  -= 20
            reason  = "Respons terpotong (truncated)"

        # ── 5. Incomplete code block ──────────────────────────────
        open_fences  = response.count("```")
        if open_fences % 2 != 0:
            score  -= 20
            reason  = "Code block tidak tertutup (response mungkin terpotong)"

        return max(0, score), reason


# ─────────────────────────────────────────────────────────────────
# SINGLETON
# ─────────────────────────────────────────────────────────────────
_registry_instance = OpenRouterRegistry()


def get_registry() -> OpenRouterRegistry:
    return _registry_instance
