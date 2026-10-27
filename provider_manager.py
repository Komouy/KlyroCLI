"""
provider_manager.py — Dynamic AI Provider & API Key Manager for Klyro
Persists provider selections and API keys across sessions in klyro_config.json.
"""
import os
import json
from typing import Optional
from config import GEMINI_API_KEY, GROQ_API_KEY

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "klyro_config.json")


# Provider Catalog & Defaults
PROVIDER_CATALOG = {
    "gemini": {
        "name": "Google Gemini",
        "tag": "▲ Free • Best Free Tier & Long Context (1M)",
        "base_url": None,
        "default_model": "gemini-3.6-flash",
        "models": [
            {"id": "gemini-3.8-flash",         "desc": "★ Flagship 2026 • Engineered for Software Engineering & Agents"},
            {"id": "gemini-4-argon",           "desc": "◈ Frontier Flagship • Deep Reasoning & 1M Output Decodes"},
            {"id": "gemini-3.6-flash",         "desc": "▲ Stable Agentic • Fast, Smart & 1M Context"},
            {"id": "gemini-3.5-flash-lite",    "desc": "⌁ Ultra Lightweight • High Speed & Low Latency"},
            {"id": "gemini-3.1-flash-lite",    "desc": "⌁ Frontier-Class Lite • Cost-Efficient Performance"},
            {"id": "gemini-3.1-pro-preview",   "desc": "◈ Complex Reasoning • Large Architectures & Logic"},
            {"id": "gemini-2.5-flash",         "desc": "▲ Legacy Stable 2.5 • Fast Multimodal Reasoning"},
            {"id": "gemini-2.5-pro",           "desc": "◈ Legacy Stable 2.5 • Complex Tasks & Deep Coding"},
            {"id": "gemini-2.0-flash",         "desc": "⌁ Deprecated 2.0 • Replaced by 3.8 Flash"},
            {"id": "gemini-1.5-flash",         "desc": "⌁ Stable 1.5 Flash • 1M Context Window"},
            {"id": "gemini-1.5-pro",           "desc": "◈ Stable 1.5 Pro • 2M Context Window"},
        ],
        "key_env": "GEMINI_API_KEY",
        "key_placeholder": "AQ..."
    },
    "groq": {
        "name": "Groq LPU",
        "tag": "⌁ Free • Ultra Fast ~500 tok/s (120B / Qwen)",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "openai/gpt-oss-120b",
        "models": [
            {"id": "llama-3.3-70b-versatile",  "desc": "★ Flagship 70B • Best for Coding, Debugging & Analysis"},
            {"id": "llama-3.1-8b-instant",     "desc": "⌁ Ultra Fast Instant • 8B Low Latency Scripting"},
            {"id": "deepseek-r1-distill-llama-70b", "desc": "◈ DeepSeek R1 Distill • Complex Logic & Reasoning"},
            {"id": "mixtral-8x7b-32768",       "desc": "▲ Mixtral MoE • 32K Context Window"},
            {"id": "qwen-qwq-32b",             "desc": "◈ QwQ 32B • Reasoning & Math Specialist"},
            {"id": "openai/gpt-oss-120b",      "desc": "★ Best for Coding • Flagship 120B Open-Source"},
            {"id": "groq/compound-mini",       "desc": "⌁ Lightweight & Fast • File Edits & Quick Refactors"},
            {"id": "qwen/qwen3.8-27b",         "desc": "◈ Strong Logic & Math • Accurate for Algorithms"},
            {"id": "groq/compound",            "desc": "▲ Multi-Agent Flagship • Deep Code Analysis"},
            {"id": "openai/gpt-oss-20b",       "desc": "⌁ Fast & Efficient • Low-latency Scripting"},
            {"id": "qwen/qwen3.6-27b",         "desc": "◈ Stable Baseline • General Programming"},
        ],
        "key_env": "GROQ_API_KEY",
        "key_placeholder": "gsk_..."
    },
    "claude": {
        "name": "Anthropic Claude",
        "tag": "▲ Frontier • Claude 3.7 Sonnet, 3.5 Sonnet & Haiku",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-3-7-sonnet-20250219",
        "models": [
            {"id": "claude-3-7-sonnet-20250219", "desc": "★ Flagship 3.7 Sonnet • Hybrid Reasoning & Elite Coding"},
            {"id": "claude-3-5-sonnet-20241022", "desc": "◈ Flagship 3.5 Sonnet • State-of-the-Art Software Engineering"},
            {"id": "claude-3-5-haiku-20241022",  "desc": "⌁ Ultra Fast Haiku • Rapid Scripting & Efficient Chat"},
            {"id": "claude-3-opus-20240229",    "desc": "▲ Legacy Opus • Deep Complex Reasoning"},
        ],
        "key_env": "ANTHROPIC_API_KEY",
        "key_placeholder": "sk-ant-api03-..."
    },
    "openrouter": {
        "name": "OpenRouter",
        "tag": "◍ Smart Free Tier • Dynamic Model Discovery + Klyro Router",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "z-ai/glm-5.2:free",
        # NOTE: This static list is the fallback / seed only.
        # At runtime, get_models_list("openrouter") returns models from
        # the dynamic Klyro Model Registry (openrouter_registry.py).
        "models": [
            {"id": "z-ai/glm-5.2:free",                      "desc": "◈ GLM 5.2 Free • Complex Coding, Agent, 256K ctx [HIGH]"},
            {"id": "minimax/minimax-m3:free",                 "desc": "≋ MiniMax M3 Free • 1M Context, Multimodal, Long Agent [HIGH]"},
            {"id": "nvidia/nemotron-3-super-120b-a12b:free",  "desc": "▲ Nemotron 3 Super Free • 120B, Reasoning, Multi-agent [HEAVY]"},
            {"id": "openrouter/auto",                         "desc": "↻ OpenRouter Auto • Best available free model (simple fallback)"},
        ],
        "key_env": "OPENROUTER_API_KEY",
        "key_placeholder": "sk-or-v1-..."
    },
    "deepseek": {
        "name": "DeepSeek",
        "tag": "◈ Paid • Smart Coding & Reasoning (V3/V4)",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "models": [
            {"id": "deepseek-chat",            "desc": "★ Recommended V3 • Top-tier Coding & Chat"},
            {"id": "deepseek-reasoner",        "desc": "◈ R1 Thinking Mode • Deep Logic & Problem Solving"},
            {"id": "deepseek-v4-pro",          "desc": "▲ V4 Pro Preview • Maximum Capability"},
            {"id": "deepseek-v4-flash",        "desc": "⌁ V4 Flash • High Efficiency & Speed"},
        ],
        "key_env": "DEEPSEEK_API_KEY",
        "key_placeholder": "sk-..."
    },
    "openai": {
        "name": "OpenAI",
        "tag": "★ Paid • GPT-4o & o3-mini Flagship",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "models": [
            {"id": "gpt-4o-mini",              "desc": "★ Recommended • Fast, Intelligent & Cost-effective"},
            {"id": "gpt-4o",                   "desc": "▲ Primary Flagship • Top Accuracy & Multimodal"},
            {"id": "o3-mini",                  "desc": "◈ Specialized Reasoning • Math, Science & Deep Logic"},
            {"id": "gpt-4.1-mini",             "desc": "⌁ Next-Gen • High Precision & Speed"},
        ],
        "key_env": "OPENAI_API_KEY",
        "key_placeholder": "sk-proj-..."
    },
    "custom": {
        "name": "Custom / Ollama / LM Studio",
        "tag": "✱  Custom Endpoint — Ollama, Local Models, etc",
        "base_url": "http://localhost:11434/v1",
        "default_model": "qwen2.5:3b",
        "models": [
            {"id": "qwen2.5-coder:3b-instruct", "desc": "▩ Qwen 2.5 Coder 3B Instruct • Dedicated Local Code Generation (Recommended)"},
            {"id": "qwen2.5:3b",                "desc": "⌁ Qwen 2.5 3B • Ultra Fast Local General Chat"},
            {"id": "qwen2.5-coder",             "desc": "▩ Qwen Coder • Dedicated Local Code Generation"},
            {"id": "llama3",                    "desc": "◇ Meta Llama 3 • General Purpose Local AI"},
            {"id": "deepseek-r1",               "desc": "◈ DeepSeek R1 Local • Offline Thinking & Reasoning"},
            {"id": "phi3:mini",                 "desc": "⌁ Phi-3 Mini • Microsoft Lightweight Local"},
            {"id": "mistral",                   "desc": "FR Mistral Local • Fast & Lightweight"},
            {"id": "custom",                    "desc": "✱ Custom Model Identifier (type with /cmodel <name>)"},
        ],
        "key_env": "CUSTOM_API_KEY",
        "key_placeholder": "ollama / sk-or-..."
    }
}


# get_models_list is defined as get_provider_models below (after get_available_providers)


def get_model_ids(provider: str) -> list:
    """Return list of string IDs for a provider."""
    return [m["id"] for m in get_models_list(provider)]


def get_available_providers() -> list:
    """Return the list of provider IDs that currently have a usable API key
    configured (via klyro_config.json or their env var fallback).

    Was referenced by consensus_engine.py's collect_candidates() and by the
    /consensus toggle in klyro_cli.py but never actually defined anywhere in
    this module — calling either would raise AttributeError. This almost
    certainly went unnoticed specifically because consensus_engine.py was
    never wired into the CLI, so this code path was never exercised.
    "custom" (local Ollama, no key required) always counts as available if
    its base URL is configured, since local providers don't need a key.
    """
    available = []
    for provider_id in PROVIDER_CATALOG:
        if provider_id == "custom":
            # Local/Ollama-style endpoint — no API key required.
            available.append(provider_id)
            continue
        if get_api_key(provider_id):
            available.append(provider_id)
    return available


def get_provider_models(provider: str, force_refresh: bool = False) -> list[dict]:
    """
    Get live models list for provider using ModelCrawler and LiveModelDiscovery,
    filtering out any blacklisted dead models.
    Falls back to static PROVIDER_CATALOG if discovery is not available or fails.
    """
    try:
        from core.model_discovery import get_dead_model_manager
        dead_mgr = get_dead_model_manager()
    except Exception:
        dead_mgr = None

    if not force_refresh:
        try:
            from core.model_crawler import get_model_crawler
            crawler = get_model_crawler()
            synced = crawler.get_synced_models(provider)
            if synced:
                if dead_mgr:
                    synced = [m for m in synced if not dead_mgr.is_dead(provider, m.get("id", ""))]
                if synced:
                    return synced
        except Exception:
            pass

    try:
        from core.model_discovery import get_live_discovery
        discovered = get_live_discovery().get_models(provider, force_refresh=force_refresh)
        if discovered:
            if dead_mgr:
                discovered = [m for m in discovered if not dead_mgr.is_dead(provider, m.get("id", ""))]
            if discovered:
                return discovered
    except Exception:
        pass

    cat = PROVIDER_CATALOG.get(provider.lower(), {})
    models = cat.get("models", [])
    if dead_mgr:
        return [m for m in models if not dead_mgr.is_dead(provider, m.get("id", ""))]
    return models


# Alias for backward compatibility
get_models_list = get_provider_models


def load_config() -> dict:
    """Load config from disk with fallback defaults."""
    default_config = {
        "active_provider": "gemini",
        "active_models": {
            "gemini":     "gemini-3.6-flash",
            "claude":     "claude-3-7-sonnet-20250219",
            "deepseek":   "deepseek-chat",
            "groq":       "openai/gpt-oss-120b",
            "openrouter": "z-ai/glm-5.2:free",
            "openai":     "gpt-4o-mini",
            "custom":     "llama3",
            "cerebras":   "gpt-oss-120b",
        },
        "api_keys": {
            "gemini":     GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", ""),
            "claude":     os.getenv("ANTHROPIC_API_KEY", os.getenv("CLAUDE_API_KEY", "")),
            "deepseek":   os.getenv("DEEPSEEK_API_KEY", ""),
            "groq":       GROQ_API_KEY or os.getenv("GROQ_API_KEY", ""),
            "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
            "openai":     os.getenv("OPENAI_API_KEY", ""),
            "custom":     os.getenv("CUSTOM_API_KEY", ""),
            "cerebras":   os.getenv("CEREBRAS_API_KEY", ""),
        },
        "custom_base_url": "http://localhost:11434/v1"
    }



    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Merge with default keys to avoid MissingKey errors
                for k, v in default_config.items():
                    if k not in data:
                        data[k] = v
                    elif isinstance(v, dict):
                        for sub_k, sub_v in v.items():
                            if sub_k not in data[k]:
                                data[k][sub_k] = sub_v
                return data
        except Exception:
            return default_config
    return default_config


def save_config(config_data: dict):
    """Save config to JSON file with automatic credential sanitization.

    This file stores API keys in plaintext (see class docstring). It's not
    encrypted — that's a real limitation, not something a chmod fixes — but
    on POSIX we at least restrict it to owner-only read/write so other
    local users on a shared machine can't read it. No-op on Windows.
    """
    try:
        # Sanitize API keys and URLs
        if isinstance(config_data.get("api_keys"), dict):
            for prov, key in config_data["api_keys"].items():
                if isinstance(key, str):
                    config_data["api_keys"][prov] = key.strip()

        if "custom_base_url" in config_data and isinstance(config_data["custom_base_url"], str):
            clean_url = config_data["custom_base_url"].strip()
            if clean_url and not (clean_url.startswith("http://") or clean_url.startswith("https://")):
                clean_url = "http://" + clean_url
            config_data["custom_base_url"] = clean_url

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except Exception:
            pass  # Best-effort; e.g. unsupported on this filesystem/OS
        return True
    except Exception as e:
        print(f"[Config Error] {friendly('Could not save the configuration', e)}")
        return False


def get_api_key(provider: str) -> str:
    """Get API key for specific provider."""
    cfg = load_config()
    key = cfg.get("api_keys", {}).get(provider, "")
    if not key:
        env_var = PROVIDER_CATALOG.get(provider, {}).get("key_env")
        if env_var:
            key = os.getenv(env_var, "")
    return key.strip() if isinstance(key, str) else ""


def set_api_key(provider: str, api_key: str):
    """Set API key for provider."""
    cfg = load_config()
    if "api_keys" not in cfg:
        cfg["api_keys"] = {}
    cfg["api_keys"][provider] = (api_key or "").strip()
    save_config(cfg)


def probe_ollama_endpoint(base_url: str = "http://localhost:11434/v1", timeout: float = 1.5) -> tuple[bool, str]:
    """
    Probe if local Ollama/custom OpenAI-compatible endpoint is running and responding.
    Returns: (is_online: bool, message: str)
    """
    import urllib.request
    import urllib.error
    url = (base_url or "http://localhost:11434/v1").strip().rstrip("/") + "/models"
    if not url.startswith("http"):
        url = "http://" + url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "KlyroCLI/Probe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status in (200, 204):
                return True, "Ollama service is active and responsive."
            return True, f"Ollama endpoint responded with HTTP {resp.status}."
    except urllib.error.HTTPError as e:
        return True, f"Ollama endpoint reached (HTTP {e.code})."
    except Exception as e:
        return False, f"Ollama endpoint unreachable at {base_url}. Make sure 'ollama serve' or your local LLM app is running."


def validate_api_key_format(provider: str, key: str) -> tuple[bool, str]:
    """
    Validate the format and integrity of an API key offline before attempting network calls.
    Detects known dummy placeholders, invalid prefixes, or suspicious lengths.
    Returns: (is_valid: bool, reason: str)
    """
    if not key or not isinstance(key, str):
        return False, "API key cannot be empty."

    clean_key = key.strip()
    if not clean_key:
        return False, "API key cannot be empty."

    # Dummy / placeholder detection
    lower_key = clean_key.lower()
    dummy_patterns = [
        "your_key", "your-key", "your_api", "your-api",
        "placeholder", "dummy", "test_key", "testkey", "cleankey",
        "example", "xxx", "sk-..."
    ]
    if any(p in lower_key for p in dummy_patterns):
        return False, "Key terdeteksi sebagai placeholder atau dummy test value."

    if provider == "gemini":
        if not clean_key.startswith("AQ"):
            return False, "Gemini API key harus diawali dengan 'AQ'."
        if len(clean_key) < 25:
            return False, f"Gemini API key terlalu pendek ({len(clean_key)} karakter)."
    elif provider == "groq":
        if not clean_key.startswith("gsk_"):
            return False, "Groq API key harus diawali dengan 'gsk_'."
        if len(clean_key) < 30:
            return False, f"Groq API key terlalu pendek ({len(clean_key)} karakter)."
    elif provider == "openrouter":
        if not clean_key.startswith("sk-or-v1-"):
            return False, "OpenRouter API key harus diawali dengan 'sk-or-v1-'."
        if len(clean_key) < 35:
            return False, f"OpenRouter API key terlalu pendek ({len(clean_key)} karakter)."
    elif provider in ("claude", "anthropic"):
        if not clean_key.startswith("sk-ant-"):
            return False, "Anthropic Claude API key harus diawali dengan 'sk-ant-'."
        if len(clean_key) < 25:
            return False, f"Anthropic Claude API key terlalu pendek ({len(clean_key)} karakter)."
    elif provider == "cerebras":
        if not clean_key.startswith("csk-"):
            return False, "Cerebras API key harus diawali dengan 'csk-'."
        if len(clean_key) < 25:
            return False, f"Cerebras API key terlalu pendek ({len(clean_key)} karakter)."
    elif provider in ("openai", "deepseek"):
        if not (clean_key.startswith("sk-") or clean_key.startswith("sk-proj-")):
            return False, f"{provider.capitalize()} API key harus diawali dengan 'sk-'."
        if len(clean_key) < 20:
            return False, f"{provider.capitalize()} API key terlalu pendek ({len(clean_key)} karakter)."
    elif provider == "custom":
        return True, "Valid"

    return True, "Valid"


def probe_provider_key(provider: str, key: str, custom_url: Optional[str] = None, timeout: float = 3.5) -> tuple[bool, str, float]:
    """
    Perform a fast live handshake to verify credentials against the provider API.
    Returns: (is_valid: bool, message: str, latency_ms: float)
    """
    import time
    import urllib.request
    import urllib.error

    if provider == "custom":
        t0 = time.time()
        ok, msg = probe_ollama_endpoint(custom_url or "http://localhost:11434/v1", timeout=timeout)
        lat = (time.time() - t0) * 1000
        return ok, msg, lat

    clean_key = (key or "").strip()
    if not clean_key:
        return False, "No API key configured.", 0.0

    t0 = time.time()
    try:
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={clean_key}&pageSize=1"
            req = urllib.request.Request(url, headers={"User-Agent": "KlyroCLI/Handshake"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                lat = (time.time() - t0) * 1000
                if resp.status == 200:
                    return True, "Google Gemini credentials verified.", lat
                return True, f"HTTP {resp.status}", lat
        elif provider in ("claude", "anthropic"):
            url = "https://api.anthropic.com/v1/models"
            headers = {
                "x-api-key": clean_key,
                "anthropic-version": "2023-06-01",
                "User-Agent": "KlyroCLI/Handshake"
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                lat = (time.time() - t0) * 1000
                if resp.status == 200:
                    return True, "Anthropic Claude credentials verified.", lat
                return True, f"HTTP {resp.status}", lat
        else:
            cat = PROVIDER_CATALOG.get(provider, {})
            base_url = cat.get("base_url")
            if not base_url:
                return False, f"Unknown base URL for provider '{provider}'.", 0.0

            url = base_url.rstrip("/") + "/models"
            headers = {
                "Authorization": f"Bearer {clean_key}",
                "User-Agent": "KlyroCLI/Handshake"
            }
            if provider == "openrouter":
                headers["HTTP-Referer"] = "https://github.com/dhavi/KlyroCLI"
                headers["X-Title"] = "KlyroCLI"

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                lat = (time.time() - t0) * 1000
                if resp.status in (200, 204):
                    return True, f"{cat.get('name', provider)} credentials verified.", lat
                return True, f"HTTP {resp.status}", lat

    except urllib.error.HTTPError as e:
        lat = (time.time() - t0) * 1000
        if e.code in (400, 401, 403):
            return False, f"API key ditolak ({e.code} Unauthorized/Invalid Key).", lat
        elif e.code == 429:
            return False, f"Rate limit / kuota habis ({e.code} Too Many Requests).", lat
        return False, f"Server merespons dengan HTTP {e.code}.", lat
    except urllib.error.URLError as e:
        lat = (time.time() - t0) * 1000
        return False, f"Koneksi jaringan gagal: {e.reason}", lat
    except Exception as e:
        lat = (time.time() - t0) * 1000
        return False, f"Koneksi gagal: {e}", lat


def get_active_provider() -> tuple:
    """Return (active_provider, active_model, base_url, api_key)."""
    cfg = load_config()
    provider = cfg.get("active_provider", "gemini")
    cat = PROVIDER_CATALOG.get(provider, PROVIDER_CATALOG["gemini"])

    model = cfg.get("active_models", {}).get(provider, cat["default_model"])
    api_key = get_api_key(provider)

    if provider == "custom":
        base_url = cfg.get("custom_base_url", "http://localhost:11434/v1")
    else:
        base_url = cat.get("base_url")

    return provider, model, base_url, api_key


def set_active_provider(provider: str, model: Optional[str] = None, custom_url: Optional[str] = None):
    """Set active provider and optionally model/custom URL."""
    if provider not in PROVIDER_CATALOG:
        return False, f"Unknown provider '{provider}'."

    cfg = load_config()
    cfg["active_provider"] = provider

    cat = PROVIDER_CATALOG[provider]
    if model:
        cfg["active_models"][provider] = model.strip()
    elif provider not in cfg["active_models"]:
        cfg["active_models"][provider] = cat["default_model"]

    if custom_url and provider == "custom":
        cfg["custom_base_url"] = custom_url.strip()

    save_config(cfg)
    return True, f"Provider set to {cat['name']} ({cfg['active_models'][provider]})"
