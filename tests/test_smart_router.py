"""
tests/test_smart_router.py — Unit Tests for Universal Workload-Based Smart Router
"""

import pytest
from core.smart_router import (
    WorkloadTier,
    classify_workload,
    SmartRouter,
    get_smart_router,
)


def test_classify_workload_light():
    tier, reason = classify_workload("halo apa kabar")
    assert tier == WorkloadTier.LIGHT

    tier, reason = classify_workload("bagaimana cara keluar dari CLI?")
    assert tier == WorkloadTier.LIGHT

    tier, reason = classify_workload("")
    assert tier == WorkloadTier.LIGHT


def test_classify_workload_code():
    tier, reason = classify_workload("buatkan fungsi binary search di python")
    assert tier == WorkloadTier.CODE

    tier, reason = classify_workload("perbaiki error IndexError pada file user_service.py")
    assert tier == WorkloadTier.CODE

    tier, reason = classify_workload("tulis unit test untuk authentication controller")
    assert tier == WorkloadTier.CODE


def test_classify_workload_reasoning():
    tier, reason = classify_workload("apa kompleksitas big-o algoritma ini dan bagaimana optimasi deadlock?")
    assert tier == WorkloadTier.REASONING

    tier, reason = classify_workload("analisis mendalam akar penyebab race condition pada worker thread")
    assert tier == WorkloadTier.REASONING


def test_classify_workload_heavy():
    # 1. By keyword
    tier, reason = classify_workload("audit seluruh arsitektur proyek ini dan refaktor seluruh file")
    assert tier == WorkloadTier.HEAVY

    # 2. By context size (>45K chars with coding query)
    tier, reason = classify_workload("refactor function ini", context_chars=60_000, file_count=15)
    assert tier == WorkloadTier.HEAVY


def test_smart_router_route(monkeypatch):
    router = SmartRouter()

    # Mock configured providers (simulate user having Gemini, Groq, OpenRouter keys)
    monkeypatch.setattr(
        router,
        "get_configured_providers",
        lambda: {
            "gemini": "AIzaSyMockKey",
            "groq": "gsk_MockKey",
            "openrouter": "sk-or-v1-MockKey",
        },
    )

    # 1. Light query -> Groq (Speed)
    prov, model, reason, tier = router.route("halo apa kabar")
    assert prov == "groq"
    assert tier == WorkloadTier.LIGHT

    # 2. Code query -> Groq Flagship 120B or Mistral Codestral
    prov, model, reason, tier = router.route("buatkan fungsi filter data pelanggan")
    assert prov in ["groq", "openrouter"]
    assert tier == WorkloadTier.CODE

    # 3. Heavy query -> Gemini (1M Context)
    prov, model, reason, tier = router.route("audit seluruh arsitektur proyek")
    assert prov == "gemini"
    assert tier == WorkloadTier.HEAVY


def test_smart_router_manual_override(monkeypatch):
    router = SmartRouter()
    monkeypatch.setattr(
        router,
        "get_configured_providers",
        lambda: {"gemini": "mock_key", "groq": "mock_key"},
    )

    # With manual override, should honor user's chosen provider
    prov, model, reason, tier = router.route("halo apa kabar", manual_override="gemini")
    assert prov == "gemini"
    assert "Manual Override" in reason


def test_smart_router_fallback_cascade(monkeypatch):
    router = SmartRouter()
    monkeypatch.setattr(
        router,
        "get_configured_providers",
        lambda: {
            "groq": "key1",
            "openrouter": "key2",
            "gemini": "key3",
        },
    )

    # If groq fails for CODE tier, should cascade to openrouter or gemini
    fallbacks = router.get_fallback_candidates(WorkloadTier.CODE, failed_provider="groq")
    assert len(fallbacks) >= 2
    fallback_provs = [f[0] for f in fallbacks]
    assert "groq" not in fallback_provs
    assert "openrouter" in fallback_provs
    assert "gemini" in fallback_provs


def test_smart_router_temp_exclusion(monkeypatch):
    router = SmartRouter()
    monkeypatch.setattr(
        router,
        "get_configured_providers",
        lambda: {"groq": "key1", "gemini": "key2"},
    )

    # Exclude groq
    router.temp_exclude_provider("groq")
    prov, model, reason, tier = router.route("halo apa kabar")
    assert prov != "groq"
    assert prov == "gemini"

    # Reset
    router.reset_exclusions()
    prov, model, reason, tier = router.route("halo apa kabar")
    assert prov == "groq"
