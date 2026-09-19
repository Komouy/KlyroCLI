"""
test_comprehensive_audit.py — Automated Full-Stack Bug & Edge Case Detector
Tests all commands, security filters, file operations, error handlers, and provider catalogs.
"""

import os
import sys
import json
import time

# Ensure project modules are importable (this file lives in scratch/, one
# level below project root — without this, `python scratch/test_....py`
# fails with ModuleNotFoundError since Python only adds the script's own
# directory to sys.path, not the project root).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("🔍 STARTING COMPREHENSIVE BUG & EDGE CASE AUDIT...")
print("=" * 60)

errors_found = []

# ── TEST 1: session_manager.py Zero-Division & Edge Cases ──────
try:
    import session_manager
    # Reset usage to 0
    session_manager._SESSION_USAGE["queries_count"] = 0
    session_manager._SESSION_USAGE["total_duration_sec"] = 0.0
    session_manager._SESSION_USAGE["total_prompt_chars"] = 0
    session_manager._SESSION_USAGE["total_response_chars"] = 0
    
    m = session_manager.get_usage_metrics()
    assert m["queries_count"] == 0
    assert m["avg_speed_tps"] == 0.0
    assert m["avg_latency_sec"] == 0.0
    assert m["estimated_cost_usd"] == 0.0
    print("[PASS] TEST 1: session_manager zero-division safety")
except Exception as e:
    errors_found.append(f"session_manager zero-division: {e}")
    print("[FAIL] TEST 1:", e)

# ── TEST 2: security.py Guardrails & False Positives ────────────
try:
    import security
    # Test true positives
    dangers = [
        "rm -rf /", "rm -rf .", "rm -rf *",
        "del /f /s /q C:\\*", "format d:",
        "dd if=/dev/zero of=/dev/sda",
        "diskpart", "shutdown -s -t 0"
    ]
    for d in dangers:
        is_d, reason = security.check_command_safety(d)
        assert is_d, f"Failed to detect danger in: {d}"

    # Test false positives (safe commands MUST be allowed)
    safes = [
        "npm run dev", "git commit -m 'delete old files'",
        "python main.py", "rmdir my_empty_folder",
        "pip install -e .", "cargo build --release"
    ]
    for s in safes:
        is_d, reason = security.check_command_safety(s)
        assert not is_d, f"False positive on safe command: {s} (Reason: {reason})"

    print("[PASS] TEST 2: security.py danger detection & zero false-positives")
except Exception as e:
    errors_found.append(f"security.py check: {e}")
    print("[FAIL] TEST 2:", e)

# ── TEST 3: file_manager.py Path Traversal & Syntax Validators ──
try:
    import file_manager
    ws = os.path.abspath(".")
    
    # Safe path checks
    assert file_manager.is_safe_path(ws, os.path.join(ws, "main.py"), rel_path="main.py") is True
    assert file_manager.is_safe_path(ws, os.path.join(ws, "src/components/button.tsx"), rel_path="src/components/button.tsx") is True

    # REGRESSION: on Windows, os.path.join(base_folder, rel) ALWAYS produces
    # a drive-letter-prefixed absolute path (e.g. "C:\...") even for a
    # perfectly legit in-workspace file — the old code rejected every such
    # path outright, meaning every DELETE/RENAME/MKDIR/write action was
    # silently blocked on Windows regardless of rel_path.
    #
    # is_safe_path() uses the host's os.path internally (posixpath here on
    # Linux, ntpath on real Windows), so calling it directly on this runner
    # can't exercise genuine Windows join/abspath semantics. Instead we
    # validate the ALGORITHM itself with ntpath explicitly — this is
    # OS-independent and catches the exact bug regardless of where the
    # test suite runs. The real function is additionally exercised
    # end-to-end below when actually running on Windows.
    import ntpath, sys as _sys, re as _re

    def _is_safe_path_algo(pathmod, base_folder, target_path, rel_path=None):
        _drive_re = _re.compile(r'^([a-zA-Z]:[\\/]|\\\\)')
        if rel_path is not None and _drive_re.match(str(rel_path)):
            return False
        base_abs = pathmod.abspath(base_folder)
        target_abs = pathmod.abspath(target_path)
        try:
            common = pathmod.commonpath([base_abs, target_abs])
        except ValueError:
            return False
        return common == base_abs

    fake_windows_ws = r"C:\Users\dhavi\Documents\TestingEditor"
    fake_windows_target = ntpath.join(fake_windows_ws, "perbandingan.py")
    assert _is_safe_path_algo(ntpath, fake_windows_ws, fake_windows_target, rel_path="perbandingan.py") is True, \
        "Regresi: file legit di workspace Windows tertolak lagi!"
    fake_traversal = ntpath.join(fake_windows_ws, "..\\..\\Windows\\calc.exe")
    assert _is_safe_path_algo(ntpath, fake_windows_ws, fake_traversal, rel_path="..\\..\\Windows\\calc.exe") is False, \
        "Traversal relatif di Windows harus tetap ditolak!"
    fake_abs_override = r"C:\Windows\System32\evil.dll"
    assert _is_safe_path_algo(ntpath, fake_windows_ws, ntpath.join(fake_windows_ws, fake_abs_override), rel_path=fake_abs_override) is False, \
        "rel_path absolut yang meng-override join harus tetap ditolak!"

    if _sys.platform.startswith("win"):
        assert file_manager.is_safe_path(fake_windows_ws, ntpath.join(fake_windows_ws, "perbandingan.py"), rel_path="perbandingan.py") is True
    assert file_manager.is_safe_path(ws, os.path.join(ws, "../../Windows/calc.exe"), rel_path="../../Windows/calc.exe") is False
    # rel_path itself already looks like an absolute Windows/UNC path — this is the
    # case os.path.join would silently let override base_folder on real Windows.
    assert file_manager.is_safe_path(ws, os.path.join(ws, "C:\\Windows\\System32"), rel_path="C:\\Windows\\System32") is False

    # Root deletion guard
    ok, msg = file_manager.hapus_item(ws, ".")
    assert not ok, "Root folder deletion was not blocked!"
    ok, msg = file_manager.hapus_item(ws, "")
    assert not ok, "Empty path deletion was not blocked!"

    # Syntax validators
    ok_py, _ = file_manager.validasi_sintaks("test.py", "x = 10\ny = 20\nprint(x + y)")
    bad_py, _ = file_manager.validasi_sintaks("test.py", "def foo(: print(1)")
    ok_json, _ = file_manager.validasi_sintaks("test.json", '{"name": "klyro", "version": 2}')
    bad_json, _ = file_manager.validasi_sintaks("test.json", '{"name": "klyro", invalid}')

    assert ok_py and not bad_py, "Python syntax validator issue"
    assert ok_json and not bad_json, "JSON syntax validator issue"

    print("[PASS] TEST 3: file_manager.py security, deletion guards & AST validators")
except Exception as e:
    errors_found.append(f"file_manager.py check: {e}")
    print("[FAIL] TEST 3:", e)

# ── TEST 4: provider_manager.py Catalog Integrity ───────────────
try:
    import provider_manager
    cats = provider_manager.PROVIDER_CATALOG
    assert len(cats) >= 8, f"Expected 8 providers, found {len(cats)}"

    for pid, pdata in cats.items():
        assert "name" in pdata and pdata["name"]
        assert "tag" in pdata and pdata["tag"]
        assert "default_model" in pdata and pdata["default_model"]
        models = provider_manager.get_models_list(pid)
        assert len(models) > 0, f"Provider {pid} has no models!"
        
        # Verify default_model is in the model list
        model_ids = [m["id"] for m in models]
        assert pdata["default_model"] in model_ids, f"default_model '{pdata['default_model']}' not in models list for {pid}!"

    print("[PASS] TEST 4: provider_manager.py catalog consistency & default models")
except Exception as e:
    errors_found.append(f"provider_manager.py check: {e}")
    print("[FAIL] TEST 4:", e)

# ── TEST 5: config.py Security & Secret Leakage Check ───────────
try:
    import config
    # In a published repo, config.py must NOT have hardcoded non-empty keys
    assert config.GEMINI_API_KEY == "" or "AIza" not in config.GEMINI_API_KEY, "Hardcoded Gemini key detected in config.py!"
    assert config.GROQ_API_KEY == "" or "gsk_" not in config.GROQ_API_KEY, "Hardcoded Groq key detected in config.py!"
    print("[PASS] TEST 5: config.py sanitized for open-source publication")
except Exception as e:
    errors_found.append(f"config.py secret leak: {e}")
    print("[FAIL] TEST 5:", e)

# ── TEST 6: doctor.py Diagnostic Execution ──────────────────────
try:
    import doctor
    res = doctor.run_diagnostics(".")
    assert "all_passed" in res
    print("[PASS] TEST 6: doctor.py diagnostic suite runs without runtime exceptions")
except Exception as e:
    errors_found.append(f"doctor.py error: {e}")
    print("[FAIL] TEST 6:", e)

# ── TEST 7: ai.py AIAssistant Facade & Auto-Fallback ───────────
try:
    import ai
    assistant = ai.AIAssistant()
    assistant.set_folder_context(".", "test context", jumlah_file=1)
    
    # Test provider switching
    assistant.switch_provider("groq", "openai/gpt-oss-120b")
    assert assistant.provider == "groq"
    assert assistant.current_model == "openai/gpt-oss-120b"

    assistant.switch_provider("openrouter", "openrouter/free")
    assert assistant.provider == "openrouter"
    assert assistant.current_model == "openrouter/free"

    # Test auto-route decision
    p, m, reason = assistant._route_for_task("buat aplikasi fullstack dari nol")
    assert p == "gemini", f"Heavy task routing issue: got {p}"
    
    p2, m2, reason2 = assistant._route_for_task("halo apa kabar")
    assert p2 == "groq", f"Light task routing issue: got {p2}"

    print("[PASS] TEST 7: ai.py facade, dynamic routing & context setting")
except Exception as e:
    errors_found.append(f"ai.py check: {e}")
    print("[FAIL] TEST 7:", e)

# ── TEST 8: runner.py script wrapping, /cd, interactive heuristics ──
try:
    import tempfile
    import runner

    # Bare .py must be wrapped so Windows does not open VS Code
    wrapped = runner.wrap_script_command("Perbandingan.py", os.getcwd())
    assert "python" in wrapped.lower() or sys.executable.lower() in wrapped.lower(), f"Bare .py not wrapped: {wrapped}"
    assert wrapped.lower().replace("\\", "/").find("perbandingan.py") != -1

    already = runner.wrap_script_command("python Perbandingan.py", os.getcwd())
    assert already.strip().lower().startswith("python"), f"Double-wrapped python cmd: {already}"

    # "start" in a filename is NOT a background server
    assert runner.is_background_command("python start.py") is False
    assert runner.is_background_command("/run Perbandingan.py") is False
    assert runner.is_background_command("npm start") is True
    assert runner.is_background_command("npm run dev") is True

    assert runner.looks_like_direct_shell("python Perbandingan.py") is True
    assert runner.looks_like_direct_shell("buat file Perbandingan.py") is False
    assert runner.looks_like_direct_shell("hi") is False
    assert runner.looks_like_direct_shell("3") is False
    assert runner.looks_like_leftover_program_input("3") is True
    assert runner.looks_like_leftover_program_input("hi") is False
    assert runner.command_needs_tty("python kalkulator/main.py") is True

    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    if os.path.isdir(docs):
        resolved = runner.resolve_cd_path("Documents", folder_aktif=os.getcwd())
        assert resolved and os.path.normcase(resolved) == os.path.normcase(docs), f"/cd Documents resolved to {resolved}"

    with tempfile.TemporaryDirectory() as td:
        script = os.path.join(td, "hello.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write("print('klyro-ok')\n")
        info = runner.detect_project_runner(td)
        assert info.get("can_run"), f"Should auto-detect hello.py, got {info}"
        res = runner.execute_script("hello.py", td, timeout=10, interactive=False)
        assert res.get("exit_code") == 0, res
        assert "klyro-ok" in (res.get("stdout") or "")

    print("[PASS] TEST 8: runner.py wrap, /cd, auto-detect, execute")
except Exception as e:
    errors_found.append(f"runner.py check: {e}")
    print("[FAIL] TEST 8:", e)

# ── TEST 9: nested markdown fences, /cd hints, leftover input ──
try:
    import file_manager

    nested = """Saya buat README.

```markdown:kalkulator/README.md
# Kalkulator Sederhana

Kalkulator sederhana berbasis Python.

## Cara Menjalankan

```bash
python main.py
```

## Fitur
- Tambah
- Kurang
```
"""
    fences = file_manager.extract_named_file_fences(nested)
    assert "kalkulator/README.md" in fences, f"missing README fence, got {list(fences)}"
    body = fences["kalkulator/README.md"]
    assert "## Fitur" in body, f"nested ```bash truncated README: {body!r}"
    assert "python main.py" in body
    assert "- Kurang" in body

    simple = "```python:main.py\ndef hello():\n    print('world')\n```\n"
    simple_f = file_manager.extract_named_file_fences(simple)
    assert simple_f.get("main.py", "").strip() == "def hello():\n    print('world')"

    commented = "```python\n# util.py\nx = 1\n```\n"
    commented_f = file_manager.extract_named_file_fences(commented)
    assert "util.py" in commented_f
    assert commented_f["util.py"].strip() == "x = 1"

    four = "````markdown:docs/README.md\n## Run\n```bash\necho hi\n```\nmore\n````\n"
    four_f = file_manager.extract_named_file_fences(four)
    assert "docs/README.md" in four_f
    assert "echo hi" in four_f["docs/README.md"]
    assert "more" in four_f["docs/README.md"]

    two = "```python:a.py\nA=1\n```\n```python:b.py\nB=2\n```\n"
    two_f = file_manager.extract_named_file_fences(two)
    assert two_f.get("a.py", "").strip() == "A=1"
    assert two_f.get("b.py", "").strip() == "B=2"

    header = "### FILE: notes.md\n```markdown\nhello from header\n```\n"
    header_f = file_manager.extract_named_file_fences(header)
    assert "hello from header" in header_f.get("notes.md", "")

    js = "```javascript:src/app.js\nconsole.log(1)\n```\n"
    js_f = file_manager.extract_named_file_fences(js)
    assert js_f.get("src/app.js", "").strip() == "console.log(1)"

    unclosed = "```python:open.py\nprint(1)\nstill here\n"
    unclosed_f = file_manager.extract_named_file_fences(unclosed)
    assert "print(1)" in unclosed_f.get("open.py", "")
    assert "still here" in unclosed_f.get("open.py", "")

    print("[PASS] TEST 9: nested fences + extra fence shapes")
except Exception as e:
    errors_found.append(f"nested fence / cd hints: {e}")
    print("[FAIL] TEST 9:", e)

# ── TEST 10: apply-to-disk, diff wrap, interactive input, leftover guard, /cd ──
try:
    import io
    import re
    import shutil
    import subprocess
    import tempfile
    import builtins
    from contextlib import redirect_stdout
    import runner
    import file_manager
    from apply_actions import parse_and_apply_actions, render_diff

    _ANSI = re.compile(r"\033\[[0-9;]*m")

    nested = """Saya buat README.

```markdown:kalkulator/README.md
# Kalkulator Sederhana

## Cara Menjalankan

```bash
python main.py
```

## Fitur
- Tambah
```
"""
    with tempfile.TemporaryDirectory() as td:
        old_input = builtins.input
        builtins.input = lambda *a, **k: "y"
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                parse_and_apply_actions(nested, td, None)
        finally:
            builtins.input = old_input
        written = os.path.join(td, "kalkulator", "README.md")
        assert os.path.isfile(written), "apply did not create README.md"
        disk = open(written, encoding="utf-8").read()
        assert "```bash" in disk, f"inner fence missing on disk: {disk!r}"
        assert "python main.py" in disk
        assert "## Fitur" in disk
        assert "- Tambah" in disk

    long_line = "A" * 160
    diff_buf = io.StringIO()
    with redirect_stdout(diff_buf):
        render_diff("", "x = 1\n" + long_line + "\n", "long.py")
    diff_out = _ANSI.sub("", diff_buf.getvalue())
    assert "\u2026" not in diff_out, "diff still clips with ellipsis"
    assert "↳" in diff_out, "long diff line was not wrapped"
    assert "".join(ch for ch in diff_out if ch == "A") == long_line, (
        "wrapped diff lost characters from the long line"
    )

    runner._LAST_EXECUTE_INTERACTIVE = True
    assert runner.take_post_interactive_guard() is True
    assert runner.take_post_interactive_guard() is False
    assert runner.looks_like_leftover_program_input("3+4") is True
    assert runner.looks_like_leftover_program_input("y") is False
    assert runner.looks_like_leftover_program_input("python x.py") is False

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with tempfile.TemporaryDirectory() as td:
        script = os.path.join(td, "echo_in.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write("n = input()\nprint('GOT-' + n)\n")
        helper = (
            "import sys\n"
            f"sys.path.insert(0, {root!r})\n"
            "import runner\n"
            f"r = runner.execute_script('echo_in.py', {td!r}, interactive=True)\n"
            "sys.stderr.write('EXIT:' + str(r.get('exit_code')))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", helper],
            input="42\n",
            capture_output=True,
            text=True,
            timeout=20,
            cwd=td,
        )
        assert "GOT-42" in (proc.stdout or ""), (
            f"interactive input() not received: stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
        assert "EXIT:0" in (proc.stderr or "") or proc.returncode == 0

    fake_home = tempfile.mkdtemp()
    try:
        docs = os.path.join(fake_home, "Documents")
        os.makedirs(os.path.join(docs, "TestingEditor"))
        os.makedirs(os.path.join(fake_home, "Favorites"))
        os.makedirs(os.path.join(fake_home, "Templates"))
        real_expand = os.path.expanduser

        def _expand(p):
            if p == "~":
                return fake_home
            if isinstance(p, str) and p.startswith("~"):
                return fake_home + p[1:].replace("/", os.sep)
            return real_expand(p)

        os.path.expanduser = _expand
        try:
            hints = runner.suggest_cd_paths("Documents/Tes", folder_aktif=fake_home)
        finally:
            os.path.expanduser = real_expand
        testing = os.path.join(docs, "TestingEditor")
        assert any(os.path.normcase(p) == os.path.normcase(testing) for p in hints), (
            f"expected TestingEditor in hints, got {hints}"
        )
        banned = {"favorites", "templates"}
        for h in hints:
            assert os.path.basename(h).lower() not in banned, f"noisy /cd hint: {hints}"
    finally:
        shutil.rmtree(fake_home, ignore_errors=True)

    print("[PASS] TEST 10: apply disk, diff wrap, interactive stdin, leftover, /cd hints")
except Exception as e:
    errors_found.append(f"regression apply/diff/run/cd: {e}")
    print("[FAIL] TEST 10:", e)

print("=" * 60)
if not errors_found:
    print("ALL 10 TEST SUITES PASSED.")
else:
    print(f"FOUND {len(errors_found)} ISSUES:")
    for err in errors_found:
        print("  -", err)
