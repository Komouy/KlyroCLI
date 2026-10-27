"""
tests/test_router_integrity.py — Catalog & Routing Integrity + Decision Table

Two layers of protection:

1. AUDIT LAYER — runs core.router_audit offline against the code as written:
   * every (provider, model) hard-coded in TIER_PROVIDER_PREFERENCES,
     consensus_engine tables and config.py must resolve against
     provider_manager.PROVIDER_CATALOG (or the OpenRouter static list),
   * the KNOWN_DEAD_ROUTES baseline below pins the 5 routes that are currently
     dead in consensus_engine. Adding a new dead route turns
     test_no_new_dead_routes red; fixing a known one turns
     test_known_dead_routes_still_reported red — that is the signal to shrink
     the baseline list.

2. DECISION-TABLE LAYER — SmartRouter.route() across the full matrix of
     4 workload tiers x key availability {all, subset, none}
                              x disruptions {excluded provider, dead model,
                                             everything unavailable}
   asserting the exact (provider, model) or a graceful documented fallback.
   Fully offline: API keys are monkeypatched, no network is ever touched.
"""

from unittest.mock import patch

import pytest

import provider_manager
from core.router_audit import (
    audit_all,
    audit_catalog_structure,
    audit_router_tiers,
    error_signatures,
    format_report,
    resolve,
)
from core.model_discovery import DeadModelManager
from core.smart_router import (
    SmartRouter,
    TIER_PROVIDER_PREFERENCES,
    WorkloadTier,
    classify_workload,
)

TIERS = [WorkloadTier.LIGHT, WorkloadTier.CODE, WorkloadTier.REASONING, WorkloadTier.HEAVY]

# Canonical prompt per tier (verified against classify_workload keyword tables).
TIER_PROMPTS = {
    WorkloadTier.LIGHT: "halo apa kabar",
    WorkloadTier.CODE: "buatkan fungsi filter data pelanggan",
    WorkloadTier.REASONING: "analisis mendalam algoritma race condition ini",
    WorkloadTier.HEAVY: "audit seluruh arsitektur proyek",
}

ALL_KEYS = set(provider_manager.PROVIDER_CATALOG)          # every provider has a key
SUBSET_KEYS = {"groq", "gemini"}                            # partial key availability
NO_KEYS: set = set()                                        # unauthenticated


def _set_keys(monkeypatch, providers):
    """Monkeypatch provider.get_api_key; 'custom' (Ollama) needs no key by design."""
    monkeypatch.setattr(
        provider_manager,
        "get_api_key",
        lambda p: f"key-{p}" if p in providers else None,
    )


# ─────────────────────────────────────────────────────────────────
# 1. AUDIT LAYER — dead-route baseline
# ─────────────────────────────────────────────────────────────────

# Routes that are dead as of this commit (now 0 dead routes after fix).
KNOWN_DEAD_ROUTES: set = set()

KNOWN_WARNINGS: set = set()


def test_catalog_structure_is_valid():
    """PROVIDER_CATALOG must be structurally sound (keys, defaults, no dupes)."""
    errors = [f for f in audit_catalog_structure() if f.is_error]
    assert not errors, "\n".join(f"{f.provider}: {f.message}" for f in errors)


def test_router_tier_preferences_resolve():
    """Every (tier, provider, model) in TIER_PROVIDER_PREFERENCES resolves."""
    errors = [f for f in audit_router_tiers() if f.is_error]
    assert not errors, "\n".join(f"{f.source}: {f.provider}/{f.model} {f.message}" for f in errors)


def test_no_new_dead_routes():
    """Regression guard: no dead route beyond the documented baseline."""
    current = set(error_signatures())
    new = current - KNOWN_DEAD_ROUTES
    assert not new, (
        "NEW dead route(s) detected — fix the reference or extend "
        f"KNOWN_DEAD_ROUTES deliberately: {sorted(new)}"
    )


def test_known_dead_routes_still_reported():
    """Reminder baseline: a resolved entry here means it was FIXED — shrink KNOWN_DEAD_ROUTES."""
    current = set(error_signatures())
    fixed = KNOWN_DEAD_ROUTES - current
    assert not fixed, (
        "Known dead route(s) now resolve — remove them from KNOWN_DEAD_ROUTES: "
        f"{sorted(fixed)}"
    )


def test_known_warnings_still_reported():
    """Documented warnings must still be visible (same shrink-the-list contract)."""
    warned = {f.signature for f in audit_all() if not f.is_error}
    missing = KNOWN_WARNINGS - warned
    assert not missing, f"Known warning(s) disappeared — update KNOWN_WARNINGS: {sorted(missing)}"


def test_audit_report_renders():
    report = format_report(audit_all())
    assert "Catalog & Routing Integrity Audit" in report
    assert "ERROR:" in report


@pytest.mark.parametrize("provider,model,expected", [
    ("groq", "openai/gpt-oss-20b", "static"),                # LIGHT first choice
    ("groq", "definitely-not-a-model", "unknown"),
    ("openrouter", "z-ai/glm-5.2:free", "static"),
    ("openrouter", "deepseek/deepseek-r1:free", "unknown"),  # dead consensus ref
    ("custom", None, "none"),                                # provider default
])
def test_resolve_classification(provider, model, expected):
    assert resolve(provider, model) == expected


@pytest.mark.parametrize("tier", TIERS)
def test_every_tier_falls_back_to_custom(tier):
    """Design invariant: each tier's ladder must end with local Ollama fallback."""
    prefs = TIER_PROVIDER_PREFERENCES[tier]
    assert prefs, f"tier {tier.value} has no preferences"
    assert prefs[-1]["provider"] == "custom"


# ─────────────────────────────────────────────────────────────────
# 2. DECISION-TABLE LAYER — normal routing per key availability
# ─────────────────────────────────────────────────────────────────

# tier -> (expected_provider, expected_model) with ALL keys present.
EXPECTED_ALL_KEYS = {
    WorkloadTier.LIGHT: ("groq", "openai/gpt-oss-20b"),
    WorkloadTier.CODE: ("groq", "openai/gpt-oss-120b"),
    WorkloadTier.REASONING: ("deepseek", "deepseek-reasoner"),
    WorkloadTier.HEAVY: ("gemini", "gemini-4-argon"),
}

# tier -> expected route when only {groq, gemini} have keys:
#   deepseek/openrouter/cerebras/mistral drop out of the ladder.
EXPECTED_SUBSET_KEYS = {
    WorkloadTier.LIGHT: ("groq", "openai/gpt-oss-20b"),
    WorkloadTier.CODE: ("groq", "openai/gpt-oss-120b"),
    WorkloadTier.REASONING: ("gemini", "gemini-3.1-pro-preview"),
    WorkloadTier.HEAVY: ("gemini", "gemini-4-argon"),
}


@pytest.mark.parametrize("tier", TIERS)
def test_route_all_keys(tier, monkeypatch):
    _set_keys(monkeypatch, ALL_KEYS)
    router = SmartRouter()
    prov, model, reason, got_tier = router.route(TIER_PROMPTS[tier])
    assert (prov, model) == EXPECTED_ALL_KEYS[tier]
    assert got_tier == tier
    assert reason.startswith(f"[{tier.value} • "), reason


@pytest.mark.parametrize("tier", TIERS)
def test_route_subset_keys(tier, monkeypatch):
    _set_keys(monkeypatch, SUBSET_KEYS)
    router = SmartRouter()
    prov, model, reason, got_tier = router.route(TIER_PROMPTS[tier])
    assert (prov, model) == EXPECTED_SUBSET_KEYS[tier]
    assert got_tier == tier


@pytest.mark.parametrize("tier", TIERS)
def test_route_no_keys_falls_back_to_local_ollama(tier, monkeypatch):
    """No API keys anywhere: every tier must land on local custom/qwen (silent,
    offline fallback — no exception, no empty result)."""
    _set_keys(monkeypatch, NO_KEYS)
    router = SmartRouter()
    custom_default = provider_manager.PROVIDER_CATALOG["custom"]["default_model"]
    prov, model, reason, got_tier = router.route(TIER_PROMPTS[tier])
    assert (prov, model) == ("custom", custom_default)
    assert got_tier == tier
    assert "Local Ollama" in reason


def test_route_classifier_prompts_hit_expected_tiers():
    """Guards the decision table itself: canonical prompts must classify as documented."""
    for tier, prompt in TIER_PROMPTS.items():
        got, _reason = classify_workload(prompt)
        assert got == tier, f"{prompt!r} classified {got.value}, expected {tier.value}"


def test_route_manual_override_honored_when_configured(monkeypatch):
    _set_keys(monkeypatch, ALL_KEYS)
    monkeypatch.setattr(provider_manager, "load_config", lambda: {"active_models": {}})
    router = SmartRouter()
    prov, model, reason, _tier = router.route(TIER_PROMPTS[WorkloadTier.LIGHT], manual_override="openai")
    assert prov == "openai"
    assert model == provider_manager.PROVIDER_CATALOG["openai"]["default_model"]
    assert "Manual Override" in reason


def test_route_manual_override_ignored_when_not_configured(monkeypatch):
    """Override to a provider without a key must degrade to normal tier routing."""
    _set_keys(monkeypatch, SUBSET_KEYS)          # openai has no key here
    router = SmartRouter()
    prov, model, _reason, _tier = router.route(TIER_PROMPTS[WorkloadTier.LIGHT], manual_override="openai")
    assert (prov, model) == EXPECTED_SUBSET_KEYS[WorkloadTier.LIGHT]


# ─────────────────────────────────────────────────────────────────
# 3. DISRUPTION MATRIX — excluded provider / dead model shift the
#    route one rung down the SAME tier ladder (all keys present).
# ─────────────────────────────────────────────────────────────────

# (tier, first-choice provider) -> expected route after the first choice dies.
EXPECTED_AFTER_DISRUPTION = {
    (WorkloadTier.LIGHT, "groq"): ("claude", "claude-3-5-haiku-20241022"),
    (WorkloadTier.CODE, "groq"): ("openrouter", "z-ai/glm-5.2:free"),
    (WorkloadTier.REASONING, "deepseek"): ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    (WorkloadTier.HEAVY, "gemini"): ("openrouter", "nvidia/nemotron-3.5-super-vl:free"),
}


def _first_choice(monkeypatch, tier):
    """Return the (provider, model) the router picks for `tier` with all keys."""
    _set_keys(monkeypatch, ALL_KEYS)
    prov, model, _reason, _tier = SmartRouter().route(TIER_PROMPTS[tier])
    return prov, model


@pytest.mark.parametrize("tier", TIERS)
def test_route_excluded_provider_shifts_one_rung(tier, monkeypatch):
    _set_keys(monkeypatch, ALL_KEYS)
    base_prov, base_model = _first_choice(monkeypatch, tier)
    router = SmartRouter()
    prov, model, _reason, got_tier = router.route(
        TIER_PROMPTS[tier], exclude_providers=[base_prov]
    )
    assert got_tier == tier
    assert (prov, model) == EXPECTED_AFTER_DISRUPTION[(tier, base_prov)]
    assert prov != base_prov


@pytest.mark.parametrize("tier", TIERS)
def test_route_dead_model_shifts_one_rung(tier, monkeypatch, tmp_path):
    """Evicting the first-choice model must move the route one rung down,
    not crash and not silently retry the dead model."""
    _set_keys(monkeypatch, ALL_KEYS)
    base_prov, base_model = _first_choice(monkeypatch, tier)

    dead_mgr = DeadModelManager(file_path=str(tmp_path / "dead_models.json"))
    dead_mgr.evict(base_prov, base_model, "unit-test eviction")
    router = SmartRouter()
    with patch("core.model_discovery.get_dead_model_manager", return_value=dead_mgr):
        prov, model, _reason, got_tier = router.route(TIER_PROMPTS[tier])

    assert got_tier == tier
    assert (prov, model) == EXPECTED_AFTER_DISRUPTION[(tier, base_prov)]
    assert (prov, model) != (base_prov, base_model)


def test_route_temp_and_param_exclusion_combine(monkeypatch):
    """temp exclusion (429) + exclude_providers argument must both apply."""
    _set_keys(monkeypatch, ALL_KEYS)
    router = SmartRouter()
    router.temp_exclude_provider("groq")
    prov, model, _reason, tier = router.route(
        TIER_PROMPTS[WorkloadTier.LIGHT], exclude_providers=["claude"]
    )
    assert tier == WorkloadTier.LIGHT
    assert (prov, model) == ("gemini", "gemini-3.5-flash-lite")
    router.reset_exclusions()
    prov, model, _r, _t = router.route(TIER_PROMPTS[WorkloadTier.LIGHT])
    assert (prov, model) == EXPECTED_ALL_KEYS[WorkloadTier.LIGHT]


def test_route_large_context_skips_tight_tpm_providers(monkeypatch):
    """context 35k–45k: tier stays LIGHT, but groq is skipped
    in favour of a large-context provider."""
    _set_keys(monkeypatch, ALL_KEYS)
    router = SmartRouter()
    prov, model, _reason, tier = router.route(
        TIER_PROMPTS[WorkloadTier.LIGHT], context_chars=40_000, file_count=10
    )
    assert tier == WorkloadTier.LIGHT               # not yet >45k => not HEAVY
    assert (prov, model) == ("claude", "claude-3-5-haiku-20241022")


def test_route_context_over_45k_is_heavy(monkeypatch):
    _set_keys(monkeypatch, ALL_KEYS)
    router = SmartRouter()
    prov, model, _reason, tier = router.route("halo apa kabar", context_chars=60_000, file_count=20)
    assert tier == WorkloadTier.HEAVY
    assert (prov, model) == EXPECTED_ALL_KEYS[WorkloadTier.HEAVY]


def test_route_all_provider_models_dead_degrades_to_active_provider(monkeypatch, tmp_path):
    """Terminal case: only custom configured AND its model dead — route must
    still return a tuple with the documented Default Provider reason."""
    _set_keys(monkeypatch, NO_KEYS)
    custom_default = provider_manager.PROVIDER_CATALOG["custom"]["default_model"]
    dead_mgr = DeadModelManager(file_path=str(tmp_path / "dead_models.json"))
    dead_mgr.evict("custom", custom_default, "unit-test eviction")
    router = SmartRouter()
    sentinel = ("gemini", "gemini-3.6-flash", "Sentinel Active", "")
    with patch("core.model_discovery.get_dead_model_manager", return_value=dead_mgr), \
         patch.object(provider_manager, "get_active_provider", return_value=sentinel):
        prov, model, reason, tier = router.route(TIER_PROMPTS[WorkloadTier.HEAVY])
    assert (prov, model) == ("gemini", "gemini-3.6-flash")
    assert reason == "Default Provider (No other alternatives ready)"
    assert tier == WorkloadTier.HEAVY


def test_fallback_candidates_follow_tier_ladder_without_duplicates(monkeypatch):
    """Tier-ladder candidates must come first, in order; leftovers (configured
    providers absent from the tier, e.g. openai) may follow. No duplicates,
    failed provider never returned, every entry carries a concrete model."""
    _set_keys(monkeypatch, ALL_KEYS)
    router = SmartRouter()
    cands = router.get_fallback_candidates(WorkloadTier.LIGHT, failed_provider="groq")
    provs = [c[0] for c in cands]
    ladder = [
        p["provider"]
        for p in TIER_PROVIDER_PREFERENCES[WorkloadTier.LIGHT]
        if p["provider"] != "groq"
    ]
    assert provs[:len(ladder)] == ladder, f"tier ladder order broken: {provs}"
    assert set(provs[len(ladder):]) <= ALL_KEYS - set(ladder), (
        f"unexpected leftover providers: {provs[len(ladder):]}"
    )
    assert "groq" not in provs, "failed provider must not be offered as fallback"
    assert len(provs) == len(set(provs)), "duplicate fallback entries"
    assert all(c[1] for c in cands), "every fallback must carry a concrete model"


def test_route_is_deterministic(monkeypatch):
    _set_keys(monkeypatch, ALL_KEYS)
    router = SmartRouter()
    for tier in TIERS:
        first = router.route(TIER_PROMPTS[tier])
        second = router.route(TIER_PROMPTS[tier])
        assert first == second, f"route for {tier.value} is not stable"




