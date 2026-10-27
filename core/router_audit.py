"""
core/router_audit.py — Offline Catalog & Routing Integrity Auditor (no API calls).

Klyro hard-codes `(provider, model)` pairs in several independent places. When a
provider retires a model, only *some* of those places get updated, and the stale
entry becomes a dead route (404 mid-request) that the router happily selects.

This module cross-checks every reference against the catalogs/caches we can see:

  source of truth : provider_manager.PROVIDER_CATALOG
  references      : core.smart_router.TIER_PROVIDER_PREFERENCES
                    consensus_engine.FLAGSHIP_MODELS / CLASSIFIER_PRIORITY /
                                     GEMINI_FALLBACK_PAIR
                    config.MODEL_KECIL / MODEL_BESAR / GROQ_MODEL_* /
                           GROQ_MODELS_CATALOG
                    openrouter_registry.PINNED_FREE_MODELS
  live evidence   : .klyro/live_models_cache.json, .klyro/model_registry.json,
                    .klyro/dead_models.json

Severity
  ERROR → the id exists in no catalog and no cache → guaranteed dead route
  WARN  → resolvable only from live/cached data (static list stale), blacklisted
          as dead, duplicated, or a provider that no tier can ever select

Usage
  python -m core.router_audit          # human report, exit 1 when ERROR found
  from core.router_audit import audit_all
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import provider_manager

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KLYRO_DIR = os.path.join(ROOT_DIR, ".klyro")
LIVE_CACHE_FILE = os.path.join(KLYRO_DIR, "live_models_cache.json")
REGISTRY_FILE = os.path.join(KLYRO_DIR, "model_registry.json")
DEAD_MODELS_FILE = os.path.join(KLYRO_DIR, "dead_models.json")

SEV_ERROR = "ERROR"
SEV_WARN = "WARN"

REQUIRED_PROVIDER_KEYS = ("name", "base_url", "default_model", "models", "key_env")
REQUIRED_MODEL_KEYS = ("id", "desc")


@dataclass
class Finding:
    severity: str
    source: str
    provider: str
    model: str
    message: str

    @property
    def signature(self) -> str:
        """Stable identity used by regression tests to detect NEW drift."""
        return f"{self.source}|{self.provider}|{self.model}"

    @property
    def is_error(self) -> bool:
        return self.severity == SEV_ERROR


# ─────────────────────────────────────────────────────────────────
# EVIDENCE LOADERS (read-only, tolerant of missing/corrupt files)
# ─────────────────────────────────────────────────────────────────

def _load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _collect_ids(node, out: Set[str]) -> None:
    """Recursively collect every string value stored under an 'id' key."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "id" and isinstance(value, str) and value:
                out.add(value)
            else:
                _collect_ids(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_ids(item, out)


def cached_ids() -> Dict[str, Set[str]]:
    """provider -> ids seen in the live model cache (plus the OpenRouter registry)."""
    seen: Dict[str, Set[str]] = {}
    live = _load_json(LIVE_CACHE_FILE) or {}
    if isinstance(live, dict):
        for provider, payload in live.items():
            ids: Set[str] = set()
            _collect_ids(payload, ids)
            if ids:
                seen.setdefault(provider, set()).update(ids)

    registry_ids: Set[str] = set()
    _collect_ids(_load_json(REGISTRY_FILE) or {}, registry_ids)
    try:  # pinned models are always injected into the OpenRouter registry
        import openrouter_registry as or_reg
        for pin in getattr(or_reg, "PINNED_FREE_MODELS", []):
            if isinstance(pin, dict) and pin.get("id"):
                registry_ids.add(pin["id"])
    except Exception:
        pass
    if registry_ids:
        seen.setdefault("openrouter", set()).update(registry_ids)
    return seen


def dead_keys() -> Set[str]:
    """Blacklisted models, stored as '<provider>:<model>' keys."""
    return set((_load_json(DEAD_MODELS_FILE) or {}).keys())


def static_ids(provider: str) -> Set[str]:
    """Model ids declared in provider_manager.PROVIDER_CATALOG for one provider."""
    cat = provider_manager.PROVIDER_CATALOG.get(provider, {})
    ids = set()
    for item in cat.get("models", []) or []:
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
        elif isinstance(item, str) and item:
            ids.add(item)
    return ids


def resolve(provider: str, model: Optional[str]) -> str:
    """
    Classify a (provider, model) reference:
      'none'    → no model pinned (provider default will be used)
      'dead'    → explicitly blacklisted in .klyro/dead_models.json
      'static'  → declared in PROVIDER_CATALOG
      'live'    → only present in live cache / OpenRouter registry (static stale)
      'unknown' → nowhere to be found → dead route
    """
    if not model:
        return "none"
    if f"{provider.lower()}:{model}" in dead_keys():
        return "dead"
    if model in static_ids(provider):
        return "static"
    if model in cached_ids().get(provider, set()):
        return "live"
    return "unknown"


# ─────────────────────────────────────────────────────────────────
# AUDITS
# ─────────────────────────────────────────────────────────────────

def audit_catalog_structure() -> List[Finding]:
    """Structural sanity of PROVIDER_CATALOG itself."""
    findings: List[Finding] = []
    for provider, cat in provider_manager.PROVIDER_CATALOG.items():
        src = "provider_manager.PROVIDER_CATALOG"
        for key in REQUIRED_PROVIDER_KEYS:
            if key not in cat:
                findings.append(Finding(SEV_ERROR, src, provider, "-", f"missing key '{key}'"))
        if cat.get("base_url") in (None, "") and provider not in ("gemini",):
            # Gemini talks through the SDK (no base_url); anything else needs one.
            findings.append(Finding(SEV_WARN, src, provider, "-", f"base_url is {cat.get('base_url')!r}"))

        models = cat.get("models") or []
        if not models:
            findings.append(Finding(SEV_ERROR, src, provider, "-", "no models declared"))
        ids: List[str] = []
        for item in models:
            if isinstance(item, str):
                findings.append(Finding(SEV_WARN, src, provider, item, "legacy string entry (no desc)"))
                ids.append(item)
                continue
            if not isinstance(item, dict):
                findings.append(Finding(SEV_ERROR, src, provider, repr(item), "model entry is not a dict"))
                continue
            for key in REQUIRED_MODEL_KEYS:
                if not item.get(key):
                    findings.append(Finding(SEV_ERROR, src, provider, item.get("id", "?"), f"missing '{key}'"))
            mid = item.get("id", "")
            ids.append(mid)
            if mid != mid.strip() or " " in mid:
                findings.append(Finding(SEV_WARN, src, provider, mid, "id has whitespace"))
        for dup in sorted({i for i in ids if ids.count(i) > 1}):
            findings.append(Finding(SEV_WARN, src, provider, dup, "duplicate model id"))

        default = cat.get("default_model")
        if default and default not in ids:
            findings.append(Finding(SEV_ERROR, src, provider, str(default), "default_model not in catalog"))
    return findings


def _check_ref(findings: List[Finding], source: str, provider: str, model: Optional[str],
               extra_msg: str = "") -> None:
    """Append a finding when a hard-coded reference cannot be resolved."""
    if provider not in provider_manager.PROVIDER_CATALOG:
        findings.append(Finding(SEV_ERROR, source, provider, model or "-",
                                "provider is not in PROVIDER_CATALOG" + (f" — {extra_msg}" if extra_msg else "")))
        return
    status = resolve(provider, model)
    if status == "unknown":
        findings.append(Finding(SEV_ERROR, source, provider, model or "-",
                                "model id resolves nowhere (guaranteed dead route)" + (f" — {extra_msg}" if extra_msg else "")))
    elif status == "live":
        # OpenRouter and local custom endpoints are dynamic by design: their
        # authoritative list comes from the live registry / local server, so a
        # live-only hit is expected and not drift.
        if provider in ("openrouter", "custom"):
            return
        findings.append(Finding(SEV_WARN, source, provider, model or "-",
                                "only in live cache/registry — static catalog is stale" + (f" — {extra_msg}" if extra_msg else "")))
    elif status == "dead":
        findings.append(Finding(SEV_ERROR, source, provider, model or "-",
                                "blacklisted in .klyro/dead_models.json" + (f" — {extra_msg}" if extra_msg else "")))


def audit_router_tiers() -> List[Finding]:
    """TIER_PROVIDER_PREFERENCES: provider exists, model resolves, tier coverage."""
    from core.smart_router import TIER_PROVIDER_PREFERENCES, WorkloadTier

    src = "core.smart_router.TIER_PROVIDER_PREFERENCES"
    findings: List[Finding] = []
    covered_providers: Set[str] = set()

    for tier, prefs in TIER_PROVIDER_PREFERENCES.items():
        seen_providers: List[str] = []
        for pref in prefs:
            provider = pref.get("provider", "")
            model = pref.get("model")
            covered_providers.add(provider)
            if provider in seen_providers:
                findings.append(Finding(SEV_WARN, src, provider, model or "-", f"duplicated in tier {tier.value}"))
            seen_providers.append(provider)
            if not pref.get("label"):
                findings.append(Finding(SEV_WARN, src, provider, model or "-", f"empty label in tier {tier.value}"))
            _check_ref(findings, f"{src}[{tier.value}]", provider, model)

    for tier in WorkloadTier:
        if not TIER_PROVIDER_PREFERENCES.get(tier):
            findings.append(Finding(SEV_ERROR, src, tier.value, "-", "tier has no provider preferences"))

    # Coverage gap: a configured provider the router can never pick on its own.
    for provider in provider_manager.PROVIDER_CATALOG:
        if provider not in covered_providers:
            findings.append(Finding(SEV_WARN, src, provider, "-",
                                    "provider is not referenced by any tier (unreachable via Smart Router)"))
    return findings


def audit_consensus_refs() -> List[Finding]:
    """consensus_engine model tables (flagship / classifier / gemini fallback)."""
    try:
        import consensus_engine as ce
    except Exception as exc:                       # noqa: BLE001
        return [Finding(SEV_WARN, "consensus_engine", "-", "-", f"module unavailable: {exc}")]

    findings: List[Finding] = []
    for provider, model in getattr(ce, "FLAGSHIP_MODELS", {}).items():
        _check_ref(findings, "consensus_engine.FLAGSHIP_MODELS", provider, model)
    for provider, model in getattr(ce, "CLASSIFIER_PRIORITY", []):
        _check_ref(findings, "consensus_engine.CLASSIFIER_PRIORITY", provider, model)
    for provider, model in getattr(ce, "GEMINI_FALLBACK_PAIR", []):
        _check_ref(findings, "consensus_engine.GEMINI_FALLBACK_PAIR", provider, model)
    for provider, model in getattr(ce, "JUDGE_PRIORITY", []):
        _check_ref(findings, "consensus_engine.JUDGE_PRIORITY", provider, model)
    return findings


def audit_config_refs() -> List[Finding]:
    """config.py default models / catalog / thresholds vs provider catalogs."""
    import config

    findings: List[Finding] = []
    src = "config"
    for attr, provider in (
        ("MODEL_KECIL", "gemini"),
        ("MODEL_BESAR", "gemini"),
        ("GROQ_MODEL_CEPAT", "groq"),
        ("GROQ_MODEL_PINTAR", "groq"),
    ):
        value = getattr(config, attr, None)
        if value:
            _check_ref(findings, f"{src}.{attr}", provider, value)

    groq_catalog_ids = {m.get("id") for m in getattr(config, "GROQ_MODELS_CATALOG", []) if isinstance(m, dict)}
    for missing in sorted(groq_catalog_ids - static_ids("groq")):
        findings.append(Finding(SEV_WARN, f"{src}.GROQ_MODELS_CATALOG", "groq", missing or "-",
                                "listed for the /cmodel dropdown but absent from the Groq catalog"))

    ambang = getattr(config, "AMBANG_BATAS_KARAKTER", 0)
    if ambang and ambang >= 45_000:
        findings.append(Finding(SEV_WARN, f"{src}.AMBANG_BATAS_KARAKTER", "-", str(ambang),
                                "geometry: auto-upgrade threshold >= router HEAVY threshold (45,000 chars)"))
    return findings


def audit_all() -> List[Finding]:
    """Run every audit and return findings sorted ERROR-first."""
    findings: List[Finding] = []
    for audit in (audit_catalog_structure, audit_router_tiers, audit_consensus_refs, audit_config_refs):
        try:
            findings.extend(audit())
        except Exception as exc:                    # noqa: BLE001
            findings.append(Finding(SEV_ERROR, audit.__name__, "-", "-", f"audit crashed: {exc}"))
    return sorted(findings, key=lambda f: (not f.is_error, f.source, f.provider, f.model))


def error_signatures(findings: Optional[List[Finding]] = None) -> List[str]:
    """Signatures of ERROR-level findings — used as a drift-detection baseline."""
    findings = audit_all() if findings is None else findings
    return sorted({f.signature for f in findings if f.is_error})


def format_report(findings: Optional[List[Finding]] = None) -> str:
    findings = audit_all() if findings is None else findings
    errors = [f for f in findings if f.is_error]
    warns = [f for f in findings if not f.is_error]
    lines = ["KlyroCLI Catalog & Routing Integrity Audit", "=" * 46,
             f"ERROR: {len(errors)}   WARN: {len(warns)}", ""]
    for label, group in (("ERRORS (dead routes)", errors), ("WARNINGS", warns)):
        lines.append(f"── {label} ──")
        if not group:
            lines.append("  (none)")
        for f in group:
            lines.append(f"  [{f.severity}] {f.source} :: {f.provider} :: {f.model}")
            lines.append(f"      {f.message}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    findings = audit_all()
    report = format_report(findings)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print(report)
    raise SystemExit(1 if any(f.is_error for f in findings) else 0)


