"""
session_manager.py — Klyro CLI Session History & Token/Cost Usage Tracker
Tracks tokens, latency, cost estimation, and persists conversation history locally.
"""

import os
import json
import time
from datetime import datetime

# Global in-memory usage metrics for current CLI session
_SESSION_USAGE = {
    "start_time": time.time(),
    "queries_count": 0,
    "total_prompt_chars": 0,
    "total_response_chars": 0,
    "total_duration_sec": 0.0,
    "providers_used": {}
}

# Pricing estimation per 1M tokens ($ USD)
PROVIDER_PRICING = {
    "gemini":     {"prompt": 0.0,    "completion": 0.0,    "tag": "Free Tier"},
    "groq":       {"prompt": 0.0,    "completion": 0.0,    "tag": "Free Tier"},
    "cerebras":   {"prompt": 0.0,    "completion": 0.0,    "tag": "Free Tier (1M/day)"},
    "openrouter": {"prompt": 0.0,    "completion": 0.0,    "tag": "Free Models (:free)"},
    "mistral":    {"prompt": 0.0,    "completion": 0.0,    "tag": "Experiment Tier"},
    "custom":     {"prompt": 0.0,    "completion": 0.0,    "tag": "Local / Free"},
    "deepseek":   {"prompt": 0.14,   "completion": 0.28,   "tag": "Paid (V3/V4)"},
    "openai":     {"prompt": 0.15,   "completion": 0.60,   "tag": "Paid (GPT-4o mini)"},
}


def _get_history_file(folder_path: str) -> str:
    """Return path to .klyro/history.json in the workspace."""
    klyro_dir = os.path.join(os.path.abspath(folder_path), ".klyro")
    try:
        os.makedirs(klyro_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(klyro_dir, "history.json")


def record_query_usage(provider: str, model: str, prompt_text: str, response_text: str, duration_sec: float, extra_prompt_chars: int = 0):
    """Record token and performance metrics for a single query.

    extra_prompt_chars: additional characters actually sent as part of the
    request but not part of prompt_text itself — in practice, the system
    prompt (project context), which is resent in full on every turn and is
    usually far larger than what the user typed. Callers should pass the
    provider's actual system-prompt length here so /usage and cost
    estimates reflect what was really transmitted, not just the visible
    user message.
    """
    p_chars = len(prompt_text or "") + max(0, extra_prompt_chars)
    r_chars = len(response_text or "")
    
    _SESSION_USAGE["queries_count"] += 1
    _SESSION_USAGE["total_prompt_chars"] += p_chars
    _SESSION_USAGE["total_response_chars"] += r_chars
    _SESSION_USAGE["total_duration_sec"] += duration_sec

    prov_key = provider.lower()
    if prov_key not in _SESSION_USAGE["providers_used"]:
        _SESSION_USAGE["providers_used"][prov_key] = {"count": 0, "p_chars": 0, "r_chars": 0}
    
    _SESSION_USAGE["providers_used"][prov_key]["count"] += 1
    _SESSION_USAGE["providers_used"][prov_key]["p_chars"] += p_chars
    _SESSION_USAGE["providers_used"][prov_key]["r_chars"] += r_chars


def get_usage_metrics() -> dict:
    """Compute and return formatted usage metrics."""
    prompt_tokens = _SESSION_USAGE["total_prompt_chars"] // 4
    resp_tokens = _SESSION_USAGE["total_response_chars"] // 4
    total_tokens = prompt_tokens + resp_tokens
    
    q_count = _SESSION_USAGE["queries_count"]
    total_sec = _SESSION_USAGE["total_duration_sec"]
    avg_speed = (resp_tokens / total_sec) if total_sec > 0 else 0.0
    avg_latency = (total_sec / q_count) if q_count > 0 else 0.0

    # Calculate estimated cost
    total_cost = 0.0
    for prov, data in _SESSION_USAGE["providers_used"].items():
        rates = PROVIDER_PRICING.get(prov, {"prompt": 0.0, "completion": 0.0})
        p_tok = data["p_chars"] / 4.0
        r_tok = data["r_chars"] / 4.0
        cost = (p_tok / 1_000_000 * rates["prompt"]) + (r_tok / 1_000_000 * rates["completion"])
        total_cost += cost

    session_uptime = time.time() - _SESSION_USAGE["start_time"]
    mins = int(session_uptime // 60)
    secs = int(session_uptime % 60)

    return {
        "queries_count": q_count,
        "prompt_tokens": prompt_tokens,
        "response_tokens": resp_tokens,
        "total_tokens": total_tokens,
        "total_duration_sec": total_sec,
        "avg_speed_tps": avg_speed,
        "avg_latency_sec": avg_latency,
        "estimated_cost_usd": total_cost,
        "session_uptime": f"{mins}m {secs}s",
        "providers_used": _SESSION_USAGE["providers_used"]
    }


def save_interaction(folder_path: str, user_prompt: str, ai_response: str, provider: str, model: str, duration_sec: float):
    """Save an interaction into the local .klyro/history.json file."""
    if not folder_path or not os.path.exists(folder_path):
        return

    hist_file = _get_history_file(folder_path)
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider,
        "model": model,
        "duration_sec": round(duration_sec, 2),
        "prompt": user_prompt,
        "response_summary": (ai_response[:180] + "...") if len(ai_response) > 180 else ai_response
    }

    history = []
    if os.path.exists(hist_file):
        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                history = json.load(f)
                if not isinstance(history, list):
                    history = []
        except Exception:
            history = []

    history.append(entry)
    # Keep up to 100 most recent interactions
    if len(history) > 100:
        history = history[-100:]

    try:
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def load_history(folder_path: str, limit: int = 10) -> list:
    """Load recent interactions from the local .klyro/history.json file."""
    if not folder_path or not os.path.exists(folder_path):
        return []

    hist_file = _get_history_file(folder_path)
    if not os.path.exists(hist_file):
        return []

    try:
        with open(hist_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data[-limit:]
    except Exception:
        return []
    return []


def clear_history(folder_path: str) -> bool:
    """Clear local history file."""
    hist_file = _get_history_file(folder_path)
    if os.path.exists(hist_file):
        try:
            os.remove(hist_file)
            return True
        except Exception:
            return False
    return True
