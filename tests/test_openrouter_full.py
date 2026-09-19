"""
test_openrouter_full.py — Comprehensive 48-Test Suite for OpenRouter Feature
Tests: TaskProfile scoring, Smart Router routing, exclusions, quality checker,
       registry integrity, pinned models, and edge cases.

Run from project root:
    cd KlyroCLI && python scratch/test_openrouter_full.py
"""

import os
import sys

# Ensure project modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openrouter_registry import (
    OpenRouterRegistry,
    TaskProfile,
    PINNED_FREE_MODELS,
    _assign_role,
    _score_from_api_metadata,
)

# ─────────────────────────────────────────────────────────────────
# SETUP: shared registry (uses pinned + cached; no live API needed)
# ─────────────────────────────────────────────────────────────────
reg = OpenRouterRegistry()
reg.load()

PASS = 0
FAIL = 0
failures = []


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        msg = f"{label}" + (f" | {detail}" if detail else "")
        failures.append(msg)
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""))


# ═════════════════════════════════════════════════════════════════
# SUITE A — TaskProfile Scoring (14 tests)
# ═════════════════════════════════════════════════════════════════
print("\n━━━ SUITE A: TaskProfile Scoring ━━━")

# A1 — Heavy coding keyword → coding score 10
t = TaskProfile("buat aplikasi fullstack dari nol")
s = t.scores()
check("A1  Heavy coding keyword sets coding=10", s["coding"] == 10, f"got {s['coding']}")

# A2 — Heavy coding → reasoning elevated to 8
check("A2  Heavy coding elevates reasoning>=8", s["reasoning"] >= 8, f"got {s['reasoning']}")

# A3 — Heavy coding → tool_use elevated
check("A3  Heavy coding elevates tool_use>=9", s["tool_use"] >= 9, f"got {s['tool_use']}")

# A4 — Heavy coding → speed inverted to 1
check("A4  Heavy coding → speed=1 (max complexity)", s["speed"] == 1, f"got {s['speed']}")

# A5 — Light prompt → coding baseline 3
t2 = TaskProfile("halo apa kabar")
s2 = t2.scores()
check("A5  Light prompt → coding=3 (baseline)", s2["coding"] == 3, f"got {s2['coding']}")

# A6 — Light prompt → complexity label LOW
check("A6  Light prompt → complexity LOW", t2.complexity_label() == "LOW", f"got {t2.complexity_label()}")

# A7 — Medium coding keyword
t3 = TaskProfile("debug error di fungsi login")
s3 = t3.scores()
check("A7  Medium coding keyword → coding=7", s3["coding"] == 7, f"got {s3['coding']}")

# A8 — Reasoning keyword
t4 = TaskProfile("jelaskan kenapa React lebih populer dari Vue")
s4 = t4.scores()
check("A8  Reasoning keyword → reasoning=8", s4["reasoning"] == 8, f"got {s4['reasoning']}")

# A9 — Long context keyword → context=10
t5 = TaskProfile("audit semua file di proyek ini")
s5 = t5.scores()
check("A9  Long context keyword → context=10", s5["context"] == 10, f"got {s5['context']}")

# A10 — Large context_chars → context score high
t6 = TaskProfile("perbaiki kode", context_chars=120_000)
s6 = t6.scores()
check("A10 context_chars>100K → context=10", s6["context"] == 10, f"got {s6['context']}")

# A11 — Medium context_chars
t7 = TaskProfile("perbaiki kode", context_chars=50_000)
s7 = t7.scores()
check("A11 context_chars>40K → context=7", s7["context"] == 7, f"got {s7['context']}")

# A12 — file_count triggers context mid tier
t8 = TaskProfile("perbaiki kode", file_count=9)
s8 = t8.scores()
check("A12 file_count>8 → context=7", s8["context"] == 7, f"got {s8['context']}")

# A13 — complexity label HIGH for peak>=9
t9 = TaskProfile("refactor arsitektur database seluruh proyek")
check("A13 Peak>=9 → complexity HIGH", t9.complexity_label() == "HIGH", f"got {t9.complexity_label()}")

# A14 — scores() caching: same object, same dict
t10 = TaskProfile("buat fungsi authentication")
s_first  = t10.scores()
s_second = t10.scores()
check("A14 scores() returns cached dict (same object)", s_first is s_second)


# ═════════════════════════════════════════════════════════════════
# SUITE B — Smart Router: Basic Routing (8 tests)
# ═════════════════════════════════════════════════════════════════
print("\n━━━ SUITE B: Smart Router Basic Routing ━━━")

# B1 — Complex coding → GLM wins (highest coding + tool_use)
task_complex = TaskProfile("buat aplikasi fullstack dari nol")
winner = reg.route(task_complex)
check("B1  Complex coding → GLM 5.2 wins", winner["id"] == "z-ai/glm-5.2:free",
      f"got {winner['id']}")

# B2 — Long context task → MiniMax wins (context=10)
task_longctx = TaskProfile("audit seluruh proyek ini", context_chars=120_000, file_count=15)
winner2 = reg.route(task_longctx)
check("B2  Long context task → MiniMax M3 wins", winner2["id"] == "minimax/minimax-m3:free",
      f"got {winner2['id']}")

# B3 — Route returns a dict with required keys
check("B3  Route result has required keys",
      all(k in winner for k in ["id", "name", "capability", "role", "is_free"]))

# B4 — Route result is always a free model
check("B4  Route result is always free", winner.get("is_free") is True)

# B5 — Route result is never openrouter/auto (unless forced)
all_models_except_auto = [m for m in reg.all_models() if m["id"] != "openrouter/auto"]
check("B5  Route never returns auto when candidates exist", winner["id"] != "openrouter/auto")

# B6 — Require tools filter: result always has tools=True
task_tool = TaskProfile("buat file config.py dan jalankan setup")
winner_tool = reg.route(task_tool, require_tools=True)
check("B6  require_tools=True → result.tools is True",
      winner_tool is not None and winner_tool.get("tools") is True,
      f"got tools={winner_tool.get('tools') if winner_tool else None}")

# B7 — route_label returns non-empty string
label = reg.route_label(winner, task_complex)
check("B7  route_label returns non-empty string", bool(label) and len(label) > 5)

# B8 — route_label contains complexity label and model name
check("B8  route_label contains complexity + model name",
      "HIGH" in label and winner["name"] in label,
      f"got {label!r}")


# ═════════════════════════════════════════════════════════════════
# SUITE C — Smart Router: Exclusion Cascading (8 tests)
# ═════════════════════════════════════════════════════════════════
print("\n━━━ SUITE C: Exclusion Cascading ━━━")

task_c = TaskProfile("buat aplikasi fullstack dari nol")

# C1 — GLM excluded → Nemotron wins (next best for complex coding)
r_noGLM = reg.route(task_c, exclude_ids=["z-ai/glm-5.2:free"])
check("C1  Exclude GLM → Nemotron 3 Super wins",
      r_noGLM is not None and r_noGLM["id"] == "nvidia/nemotron-3-super-120b-a12b:free",
      f"got {r_noGLM['id'] if r_noGLM else None}")

# C2 — GLM + Nemotron excluded → MiniMax wins
r_noGLM_Nem = reg.route(task_c, exclude_ids=[
    "z-ai/glm-5.2:free", "nvidia/nemotron-3-super-120b-a12b:free"
])
check("C2  Exclude GLM+Nemotron → MiniMax wins",
      r_noGLM_Nem is not None and r_noGLM_Nem["id"] == "minimax/minimax-m3:free",
      f"got {r_noGLM_Nem['id'] if r_noGLM_Nem else None}")

# C3 — Excluded model never appears in result
check("C3  Excluded model never appears in result",
      r_noGLM["id"] != "z-ai/glm-5.2:free")

# C4 — Exclusion list with non-existent id: no crash
r_fake = reg.route(task_c, exclude_ids=["fake/model-xyz:free"])
check("C4  Exclusion with unknown ID doesn't crash", r_fake is not None)

# C5 — Empty exclusion list: same as no exclusion
r_empty_excl = reg.route(task_c, exclude_ids=[])
check("C5  Empty exclusion list behaves like no exclusion",
      r_empty_excl["id"] == reg.route(task_c)["id"])

# C6 — All pinned excluded → falls through to cached/auto
all_pinned_ids = [m["id"] for m in PINNED_FREE_MODELS]
r_no_pinned = reg.route(task_c, exclude_ids=all_pinned_ids)
# Should return either a discovered model or openrouter/auto (not crash)
check("C6  All pinned excluded → returns something (auto or discovered)",
      r_no_pinned is not None)

# C7 — All candidates excluded → returns openrouter/auto as last resort
all_ids = [m["id"] for m in reg.all_models() if m["id"] != "openrouter/auto"]
r_all_excl = reg.route(task_c, exclude_ids=all_ids)
check("C7  All candidates excluded → returns openrouter/auto fallback",
      r_all_excl is not None and r_all_excl["id"] == "openrouter/auto",
      f"got {r_all_excl['id'] if r_all_excl else None}")

# C8 — Long context task, MiniMax excluded → GLM takes over
task_lc2 = TaskProfile("audit seluruh proyek ini", context_chars=120_000)
r_lc_noMM = reg.route(task_lc2, exclude_ids=["minimax/minimax-m3:free"])
check("C8  Long context, no MiniMax → result is not MiniMax",
      r_lc_noMM is not None and r_lc_noMM["id"] != "minimax/minimax-m3:free",
      f"got {r_lc_noMM['id'] if r_lc_noMM else None}")


# ═════════════════════════════════════════════════════════════════
# SUITE D — Registry Integrity (8 tests)
# ═════════════════════════════════════════════════════════════════
print("\n━━━ SUITE D: Registry Integrity ━━━")

all_models = reg.all_models()

# D1 — Registry has at least 4 pinned models
pinned_in_reg = [m for m in all_models if m.get("pinned")]
check("D1  Registry contains all 4 pinned models",
      len(pinned_in_reg) >= 4, f"got {len(pinned_in_reg)}")

# D2 — Each model has required fields
required_keys = ["id", "name", "context", "is_free", "capability", "role"]
all_valid = all(all(k in m for k in required_keys) for m in all_models)
check("D2  All models have required fields", all_valid)

# D3 — No duplicate model IDs
ids = [m["id"] for m in all_models]
check("D3  No duplicate model IDs", len(ids) == len(set(ids)))

# D4 — GLM is in registry
check("D4  GLM 5.2 present in registry",
      any(m["id"] == "z-ai/glm-5.2:free" for m in all_models))

# D5 — MiniMax is in registry
check("D5  MiniMax M3 present in registry",
      any(m["id"] == "minimax/minimax-m3:free" for m in all_models))

# D6 — Nemotron is in registry
check("D6  Nemotron 3 Super present in registry",
      any(m["id"] == "nvidia/nemotron-3-super-120b-a12b:free" for m in all_models))

# D7 — get_model() returns correct model
glm = reg.get_model("z-ai/glm-5.2:free")
check("D7  get_model() returns correct model",
      glm is not None and glm["name"] == "GLM 5.2", f"got {glm}")

# D8 — get_model() returns None for unknown ID
unknown = reg.get_model("this/does-not-exist:free")
check("D8  get_model() returns None for unknown ID", unknown is None)


# ═════════════════════════════════════════════════════════════════
# SUITE E — Pinned Model Capability Validation (6 tests)
# ═════════════════════════════════════════════════════════════════
print("\n━━━ SUITE E: Pinned Model Capability Validation ━━━")

glm_pin     = next(m for m in PINNED_FREE_MODELS if m["id"] == "z-ai/glm-5.2:free")
minimax_pin = next(m for m in PINNED_FREE_MODELS if m["id"] == "minimax/minimax-m3:free")
nemotron_pin = next(m for m in PINNED_FREE_MODELS if m["id"] == "nvidia/nemotron-3-super-120b-a12b:free")

# E1 — GLM has coding=10
check("E1  GLM capability.coding == 10",
      glm_pin["capability"]["coding"] == 10)

# E2 — MiniMax has context=10 (1M context window)
check("E2  MiniMax capability.context == 10",
      minimax_pin["capability"]["context"] == 10)

# E3 — Nemotron has reasoning=10 (heavy reasoning role)
check("E3  Nemotron capability.reasoning == 10",
      nemotron_pin["capability"]["reasoning"] == 10)

# E4 — GLM context is 256K
check("E4  GLM context_length == 256_000",
      glm_pin["context"] == 256_000)

# E5 — MiniMax context is 1M
check("E5  MiniMax context_length == 1_000_000",
      minimax_pin["context"] == 1_000_000)

# E6 — All pinned models have tools=True
check("E6  All pinned models have tools=True",
      all(m["tools"] for m in PINNED_FREE_MODELS if m["id"] != "openrouter/auto"))


# ═════════════════════════════════════════════════════════════════
# SUITE F — Quality Checker (10 tests)
# ═════════════════════════════════════════════════════════════════
print("\n━━━ SUITE F: Quality Checker ━━━")

qc = reg.quality_score

# F1 — Empty response → score 0
score, _ = qc("", "buat file")
check("F1  Empty response → score=0", score == 0)

# F2 — Whitespace-only → score 0
score, _ = qc("   \n  ", "buat file")
check("F2  Whitespace-only response → score=0", score == 0)

# F3 — Very short response → score penalised
score, reason = qc("ok sure", "buat file main.py")
check("F3  Very short response → score < 70", score < 70, f"got {score}")

# F4 — Good code block with named fence → high score for coding task
good_resp = "Here is the file:\n```python:main.py\ndef hello():\n    print('world')\n```\nDone!"
score, reason = qc(good_resp, "buat file main.py")
check("F4  Named code fence for coding task → score>=70", score >= 70, f"got {score}, {reason}")

# F5 — Code block without named fence → partial penalty
unnamed_resp = "Here:\n```python\ndef foo(): pass\n```\nDone and more text here."
score, reason = qc(unnamed_resp, "buat file main.py")
check("F5  Unnamed code fence → score penalised (55<=score<85)",
      55 <= score < 85, f"got {score}, {reason}")

# F6 — Refusal phrase → score 0 (short response + refusal)
refusal_resp = "I'm sorry, I cannot help with that request."
score, _ = qc(refusal_resp, "buat file main.py")
check("F6  Refusal phrase (short) → score=0", score == 0, f"got {score}")

# F7 — Truncation signal → penalty applied
trunc_resp = "Here is some code...[truncated by system]"
score, reason = qc(trunc_resp, "buat fungsi")
check("F7  Truncation signal → score penalised", score < 80, f"got {score}")

# F8 — Unclosed code fence → penalty
unclosed = "Some code:\n```python\ndef foo(): pass"
score, reason = qc(unclosed, "buat file")
check("F8  Unclosed code fence → score penalised", score < 80, f"got {score}")

# F9 — Non-coding prompt with decent response → no code block penalty
prose_resp = "x" * 200  # long enough, no code block needed
score, reason = qc(prose_resp, "jelaskan apa itu rekursi")
check("F9  Non-coding prompt: no code block penalty → score=100", score == 100,
      f"got {score}, {reason}")

# F10 — Score never exceeds 100 and never below 0
import random
for _ in range(5):
    s, _ = qc("random " * random.randint(5, 100), "buat file atau jelaskan sesuatu")
    assert 0 <= s <= 100, f"Score out of bounds: {s}"
check("F10 Score always in [0, 100] range (5 random samples)", True)


# ═════════════════════════════════════════════════════════════════
# SUITE G — _assign_role & _score_from_api_metadata (4 tests)
# ═════════════════════════════════════════════════════════════════
print("\n━━━ SUITE G: Role Assignment & API Metadata Scoring ━━━")

# G1 — High coding + tool_use → complex_coding role
cap_coder = {"coding": 9, "reasoning": 8, "context": 6, "tool_use": 8, "speed": 3}
check("G1  coding>=9 & tool_use>=8 → complex_coding role",
      _assign_role(cap_coder, 128_000) == "complex_coding")

# G2 — 1M context → long_context_agent role (overrides coding)
cap_ctx = {"coding": 7, "reasoning": 7, "context": 10, "tool_use": 7, "speed": 7}
check("G2  context>=500K → long_context_agent role",
      _assign_role(cap_ctx, 1_000_000) == "long_context_agent")

# G3 — High reasoning → heavy_reasoning role
cap_reason = {"coding": 7, "reasoning": 9, "context": 6, "tool_use": 7, "speed": 4}
check("G3  reasoning>=9 (no high coding) → heavy_reasoning role",
      _assign_role(cap_reason, 128_000) == "heavy_reasoning")

# G4 — _score_from_api_metadata on 120B model gives coding>=8
fake_model = {
    "id": "test/bigmodel-120b:free",
    "name": "BigModel 120B",
    "context_length": 128_000,
    "supported_parameters": ["tools", "tool_choice"],
}
cap = _score_from_api_metadata(fake_model)
check("G4  120B model metadata → coding>=8 and tool_use>=8",
      cap["coding"] >= 8 and cap["tool_use"] >= 8,
      f"got coding={cap['coding']}, tool_use={cap['tool_use']}")


# ═════════════════════════════════════════════════════════════════
# RESULTS
# ═════════════════════════════════════════════════════════════════
total = PASS + FAIL
print(f"\n{'=' * 60}")
print(f"{'🎉 ALL TESTS PASSED!' if FAIL == 0 else f'⚠️  {FAIL} TEST(S) FAILED'}")
print(f"Results: {PASS}/{total} passed")
print(f"{'=' * 60}")

if failures:
    print("\nFailed tests:")
    for f in failures:
        print(f"  ✗ {f}")
    sys.exit(1)
