"""
test_validations.py — Comprehensive Unit Tests for KlyroCLI Validation Guardrails
Tests:
  1. Windows Reserved Device Names
  2. Protected Workspace Paths (.git, .env, .klyro, klyro_config.json)
  3. Atomic File Write & Cleanup
  4. Expanded Syntax Validation (Python, JSON, TOML, Delimiters, Truncation)
  5. Credential Sanitization & Ollama Probe Handling
"""

import os
import tempfile
import pytest

import file_manager
import provider_manager


# ─────────────────────────────────────────────────────────────────
# 1. WINDOWS RESERVED DEVICE NAMES
# ─────────────────────────────────────────────────────────────────
def test_windows_reserved_names_detection():
    assert file_manager.is_windows_reserved_name("con") is True
    assert file_manager.is_windows_reserved_name("con.txt") is True
    assert file_manager.is_windows_reserved_name("AUX.py") is True
    assert file_manager.is_windows_reserved_name("sub/folder/NUL.json") is True
    assert file_manager.is_windows_reserved_name("com1.log") is True
    assert file_manager.is_windows_reserved_name("lpt9") is True

    # Safe names
    assert file_manager.is_windows_reserved_name("constant.py") is False
    assert file_manager.is_windows_reserved_name("auxiliary.ts") is False
    assert file_manager.is_windows_reserved_name("main.py") is False


def test_is_safe_path_rejects_reserved_names():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = os.path.join(tmpdir, "con.py")
        assert file_manager.is_safe_path(tmpdir, target, rel_path="con.py") is False
        assert file_manager.is_safe_path(tmpdir, target) is False


# ─────────────────────────────────────────────────────────────────
# 2. PROTECTED WORKSPACE PATHS
# ─────────────────────────────────────────────────────────────────
def test_protected_workspace_paths():
    # Protected targets
    assert file_manager.is_protected_workspace_path(".git")[0] is True
    assert file_manager.is_protected_workspace_path(".git/config")[0] is True
    assert file_manager.is_protected_workspace_path(".git/HEAD")[0] is True
    assert file_manager.is_protected_workspace_path(".env")[0] is True
    assert file_manager.is_protected_workspace_path(".env.local")[0] is True
    assert file_manager.is_protected_workspace_path(".env.production")[0] is True
    assert file_manager.is_protected_workspace_path("klyro_config.json")[0] is True
    assert file_manager.is_protected_workspace_path(".klyro/model_registry.json")[0] is True

    # Safe targets
    assert file_manager.is_protected_workspace_path("src/index.js")[0] is False
    assert file_manager.is_protected_workspace_path("README.md")[0] is False
    assert file_manager.is_protected_workspace_path("config.py")[0] is False


def test_hapus_item_blocks_protected_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Attempt to delete .git
        git_dir = os.path.join(tmpdir, ".git")
        os.makedirs(git_dir, exist_ok=True)
        ok, msg = file_manager.hapus_item(tmpdir, ".git")
        assert ok is False
        assert "terlindungi" in msg or "Security" in msg
        assert os.path.exists(git_dir)

        # Attempt to delete .env
        env_file = os.path.join(tmpdir, ".env")
        with open(env_file, "w") as f:
            f.write("SECRET=123")
        ok, msg = file_manager.hapus_item(tmpdir, ".env")
        assert ok is False
        assert os.path.exists(env_file)


# ─────────────────────────────────────────────────────────────────
# 3. ATOMIC FILE WRITE
# ─────────────────────────────────────────────────────────────────
def test_atomic_file_write_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = os.path.join(tmpdir, "test_file.txt")
        ok, msg = file_manager.tulis_file(target, "Hello Atomic World", buat_backup=False)
        assert ok is True
        assert os.path.exists(target)
        with open(target, "r", encoding="utf-8") as f:
            assert f.read() == "Hello Atomic World"

        # Ensure no leftover .tmp files
        files = os.listdir(tmpdir)
        tmp_files = [f for f in files if ".tmp" in f]
        assert len(tmp_files) == 0


def test_atomic_file_write_blocks_reserved_name():
    with tempfile.TemporaryDirectory() as tmpdir:
        target = os.path.join(tmpdir, "aux.py")
        ok, msg = file_manager.tulis_file(target, "print(1)")
        assert ok is False
        assert "reserved device name" in msg


# ─────────────────────────────────────────────────────────────────
# 4. EXPANDED SYNTAX VALIDATION
# ─────────────────────────────────────────────────────────────────
def test_syntax_validation_python():
    ok, _ = file_manager.validasi_sintaks("app.py", "def foo():\n    return 42\n")
    assert ok is True

    ok, msg = file_manager.validasi_sintaks("app.py", "def foo(:\n    return 42\n")
    assert ok is False
    assert "SyntaxError" in msg


def test_syntax_validation_json():
    ok, _ = file_manager.validasi_sintaks("data.json", '{"name": "Klyro", "version": 2}')
    assert ok is True

    ok, msg = file_manager.validasi_sintaks("data.json", '{"name": "Klyro",')
    assert ok is False
    assert "JSON Error" in msg


def test_syntax_validation_toml():
    valid_toml = '[project]\nname = "KlyroCLI"\nversion = "2.5"\n'
    ok, _ = file_manager.validasi_sintaks("pyproject.toml", valid_toml)
    assert ok is True

    invalid_toml = '[project\nname = "broken"\n'
    ok, msg = file_manager.validasi_sintaks("pyproject.toml", invalid_toml)
    assert ok is False
    assert "TOML Syntax Error" in msg


def test_syntax_validation_delimiters():
    valid_js = """
    function greet(user) {
        console.log(`Hello, ${user}!`);
        return [1, 2, { ok: true }];
    }
    """
    ok, _ = file_manager.validasi_sintaks("app.js", valid_js)
    assert ok is True

    unclosed_js = """
    function greet(user) {
        if (true) {
            console.log("unfinished");
    """
    ok, msg = file_manager.validasi_sintaks("app.js", unclosed_js)
    assert ok is False
    assert "Unclosed delimiter" in msg

    mismatched_ts = "const arr = [1, 2, 3};"
    ok, msg = file_manager.validasi_sintaks("service.ts", mismatched_ts)
    assert ok is False
    assert "Mismatched delimiter" in msg or "Unmatched closing" in msg


def test_syntax_validation_destructive_truncation():
    old_code = "\n".join([f"line_{i} = {i}" for i in range(30)])
    new_code = "line_0 = 0\n"

    ok, msg = file_manager.validasi_sintaks("heavy.py", new_code, old_content=old_code)
    assert ok is False
    assert "Destructive Truncation" in msg


# ─────────────────────────────────────────────────────────────────
# 5. CREDENTIAL SANITIZATION & OLLAMA PROBE
# ─────────────────────────────────────────────────────────────────
def test_api_key_sanitization(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_config = os.path.join(tmpdir, "klyro_config.json")
        monkeypatch.setattr(provider_manager, "CONFIG_FILE", fake_config)
        provider_manager.set_api_key("gemini", "  AIzaSyCleanKey123 \n\t")
        clean = provider_manager.get_api_key("gemini")
        assert clean == "AIzaSyCleanKey123"


def test_ollama_probe_graceful_handling():
    # Probe non-existent port
    is_online, msg = provider_manager.probe_ollama_endpoint("http://127.0.0.1:59999/v1", timeout=0.5)
    assert is_online is False
    assert "unreachable" in msg.lower()


# ─────────────────────────────────────────────────────────────────
# 6. OPENROUTER STALE MODEL PROACTIVE CHECK (Priority 1)
# ─────────────────────────────────────────────────────────────────
def test_openrouter_stale_pinned_model_detection(monkeypatch):
    import openrouter_registry as or_reg

    reg = or_reg.OpenRouterRegistry()
    # Mock fetch_free_models to return a list that omits pinned models
    dummy_models = [
        {"id": "meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 70B", "context_length": 131072}
    ]
    monkeypatch.setattr(or_reg, "fetch_free_models", lambda api_key="": dummy_models)
    monkeypatch.setattr(or_reg, "_save_cache", lambda data: None)

    reg.load(force_refresh=True)
    warnings = reg.get_stale_pinned_warnings()

    # Pinned models that were not in dummy_models should be flagged as stale
    assert len(warnings) > 0
    assert any("sudah tidak tersedia" in w for w in warnings)
    # Warnings are cleared after retrieval
    assert len(reg.get_stale_pinned_warnings()) == 0


# ─────────────────────────────────────────────────────────────────
# 7. RESPONSE INTEGRITY VALIDATION (Priority 2)
# ─────────────────────────────────────────────────────────────────
def test_response_integrity_validation():
    from apply_actions import validate_ai_response_integrity

    # Valid response — no warnings
    valid_resp = (
        "Here is the updated code:\n"
        "```python:main.py\n"
        "print('hello world')\n"
        "```\n"
        "<!--ACTION:SHELL cmd=\"pytest\" -->\n"
        "<!--ACTION:DELETE path=\"old_file.py\" -->\n"
    )
    assert validate_ai_response_integrity(valid_resp) == []

    # Unclosed code fence (truncated stream)
    unclosed_resp = (
        "Starting code:\n"
        "```python:truncated.py\n"
        "def broken():\n"
        "    return 1\n"
    )
    warnings = validate_ai_response_integrity(unclosed_resp)
    assert any("Unclosed code fence" in w for w in warnings)

    # Empty file write
    empty_file_resp = (
        "```python:empty.py\n"
        "   \n"
        "```\n"
    )
    warnings = validate_ai_response_integrity(empty_file_resp)
    assert any("empty.py" in w and "empty content" in w for w in warnings)

    # Unclosed ACTION tag
    unclosed_action_resp = "<!--ACTION:SHELL cmd=\"pytest\""
    warnings = validate_ai_response_integrity(unclosed_action_resp)
    assert any("unclosed or malformed ACTION" in w for w in warnings)

    # Unknown ACTION type
    unknown_action_resp = "<!--ACTION:EXPLODE target=\"database\" -->"
    warnings = validate_ai_response_integrity(unknown_action_resp)
    assert any("Unknown ACTION type 'EXPLODE'" in w for w in warnings)

    # Missing required ACTION attributes
    missing_attrs_resp = (
        "<!--ACTION:DELETE path=\"\" -->\n"
        "<!--ACTION:RENAME from=\"a.py\" -->\n"
        "<!--ACTION:MKDIR path=\"\" -->\n"
        "<!--ACTION:SHELL cmd=\"\" -->\n"
    )
    warnings = validate_ai_response_integrity(missing_attrs_resp)
    assert any("ACTION:DELETE" in w for w in warnings)
    assert any("ACTION:RENAME" in w for w in warnings)
    assert any("ACTION:MKDIR" in w for w in warnings)
    assert any("ACTION:SHELL" in w for w in warnings)


# ─────────────────────────────────────────────────────────────────
# 8. CONTEXT SIZE PRE-FLIGHT WARNING (Priority 3)
# ─────────────────────────────────────────────────────────────────
def test_context_size_preflight_warning():
    from ai import check_context_preflight

    # Groq within limits
    assert check_context_preflight("x" * 10_000, "groq") is None

    # Groq exceeding limit (32k chars)
    warn_groq = check_context_preflight("x" * 35_000, "groq")
    assert warn_groq is not None
    assert "GROQ limit" in warn_groq and "truncated" in warn_groq

    # Custom/Ollama large context (>16k chars)
    warn_custom = check_context_preflight("x" * 20_000, "custom")
    assert warn_custom is not None
    assert "Local model context" in warn_custom

    # Cerebras exceeding limit (32k chars)
    warn_cerebras = check_context_preflight("x" * 33_000, "cerebras")
    assert warn_cerebras is not None
    assert "CEREBRAS limit" in warn_cerebras

    # DeepSeek exceeding limit (48k chars)
    warn_deepseek = check_context_preflight("x" * 50_000, "deepseek")
    assert warn_deepseek is not None
    assert "DEEPSEEK limit" in warn_deepseek

    # Gemini normal context
    assert check_context_preflight("x" * 50_000, "gemini") is None

    # Gemini extremely large context (>150k chars)
    warn_gemini = check_context_preflight("x" * 160_000, "gemini")
    assert warn_gemini is not None
    assert "very large" in warn_gemini


# ─────────────────────────────────────────────────────────────────
# 9. UNDO STACK INTEGRITY & RESILIENCE (Priority 4)
# ─────────────────────────────────────────────────────────────────
def test_undo_operation_validation():
    import undo_manager

    with tempfile.TemporaryDirectory() as tmpdir:
        folder_abs = os.path.abspath(tmpdir)

        # Valid operations
        assert undo_manager.validate_operation(
            {"type": "modify", "path": os.path.join(tmpdir, "a.py"), "old_content": "old"},
            folder_abs
        ) is True
        assert undo_manager.validate_operation(
            {"type": "create", "path": os.path.join(tmpdir, "b.py")},
            folder_abs
        ) is True
        assert undo_manager.validate_operation(
            {"type": "delete", "path": os.path.join(tmpdir, "c.py"), "old_content": "old"},
            folder_abs
        ) is True
        assert undo_manager.validate_operation(
            {"type": "rename", "src": os.path.join(tmpdir, "a.py"), "dst": os.path.join(tmpdir, "b.py")},
            folder_abs
        ) is True

        # Invalid operations
        assert undo_manager.validate_operation("not a dict", folder_abs) is False
        assert undo_manager.validate_operation({"type": "invalid_type"}, folder_abs) is False

        # Path traversal / outside workspace
        outside_path = os.path.abspath(os.path.join(tmpdir, "..", "secret.txt"))
        assert undo_manager.validate_operation(
            {"type": "modify", "path": outside_path, "old_content": "hacked"},
            folder_abs
        ) is False

        # Missing required fields
        assert undo_manager.validate_operation({"type": "rename", "src": "a.py"}, folder_abs) is False


def test_undo_transaction_record_and_apply():
    import undo_manager

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "example.txt")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Initial Content")

        # Record a modification transaction
        undo_manager.record_transaction(tmpdir, [
            {"type": "modify", "path": test_file, "old_content": "Initial Content"}
        ])
        assert undo_manager.get_undo_depth(tmpdir) == 1

        # Now simulate file change
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("Modified Content")

        # Apply undo
        ok, logs = undo_manager.apply_undo(tmpdir)
        assert ok is True
        assert any("Restored previous content" in l for l in logs)

        with open(test_file, "r", encoding="utf-8") as f:
            assert f.read() == "Initial Content"

        assert undo_manager.get_undo_depth(tmpdir) == 0

        # Ensure .klyro/undo_log.json was persisted and is valid JSON
        log_file = os.path.join(tmpdir, ".klyro", "undo_log.json")
        assert os.path.exists(log_file)
        import json
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, list)
            assert len(data) == 0  # popped back to 0


# ─────────────────────────────────────────────────────────────────
# 10. CANCELLATION MONITOR (ESC / Ctrl+C)
# ─────────────────────────────────────────────────────────────────
def test_cancellation_monitor():
    from klyro_cli import CancellationMonitor

    monitor = CancellationMonitor()
    assert monitor.cancelled_by_esc is False

    # Start and stop monitor
    monitor.start()
    assert monitor._thread is not None
    assert monitor._thread.is_alive()

    monitor.stop()
    assert not monitor._thread.is_alive()


# ─────────────────────────────────────────────────────────────────
# 11. UX API KEY VALIDATION & LIVE HANDSHAKE
# ─────────────────────────────────────────────────────────────────
def test_validate_api_key_format_valid():
    # Modern Gemini key starting with AQ or AQ.
    ok, _ = provider_manager.validate_api_key_format("gemini", "AQ." + "A" * 33)
    assert ok is True

    ok, _ = provider_manager.validate_api_key_format("gemini", "AQ" + "A" * 33)
    assert ok is True

    # Legacy Gemini key starting with AIzaSy
    ok, _ = provider_manager.validate_api_key_format("gemini", "AIzaSy" + "A" * 33)
    assert ok is True

    ok, _ = provider_manager.validate_api_key_format("groq", "gsk_" + "B" * 38)
    assert ok is True

    ok, _ = provider_manager.validate_api_key_format("openrouter", "sk-or-v1-" + "C" * 35)
    assert ok is True

    ok, _ = provider_manager.validate_api_key_format("cerebras", "csk-" + "D" * 25)
    assert ok is True

    ok, _ = provider_manager.validate_api_key_format("custom", "anything")
    assert ok is True


def test_validate_api_key_format_rejects_dummies_and_mismatches():
    # Rejects dummy values
    ok, msg = provider_manager.validate_api_key_format("gemini", "AIzaSyCleanKey123")
    assert ok is False
    assert "dummy" in msg or "placeholder" in msg

    ok, msg = provider_manager.validate_api_key_format("groq", "your_api_key_here")
    assert ok is False
    assert "dummy" in msg or "placeholder" in msg

    # Rejects prefix mismatch
    ok, msg = provider_manager.validate_api_key_format("gemini", "gsk_12345678901234567890123456789012345")
    assert ok is False
    assert "AQ" in msg or "AIza" in msg

    # Rejects empty or whitespace
    ok, msg = provider_manager.validate_api_key_format("gemini", "   ")
    assert ok is False
    assert "empty" in msg


def test_probe_provider_key_mock(monkeypatch):
    import urllib.request
    import urllib.error

    class MockResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass

    # Success mock
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=3.5: MockResponse())
    ok, msg, lat = provider_manager.probe_provider_key("gemini", "AIzaSy" + "X" * 33)
    assert ok is True
    assert "verified" in msg.lower()
    assert lat >= 0

    # HTTP 400 rejection mock
    def mock_fail(req, timeout=3.5):
        raise urllib.error.HTTPError("url", 400, "Bad Request", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", mock_fail)
    ok, msg, _ = provider_manager.probe_provider_key("gemini", "AIzaSy" + "X" * 33)
    assert ok is False
    assert "400" in msg or "ditolak" in msg.lower()


def test_syntax_validation_python_details():
    # Test valid python
    ok, msg = file_manager.validasi_sintaks("script.py", "def add(a, b):\n    return a + b\n")
    assert ok is True

    # Test syntax error includes line and details
    bad_code = "def calc():\n    x = \n    return x"
    ok, msg = file_manager.validasi_sintaks("script.py", bad_code)
    assert ok is False
    assert "SyntaxError on line 2" in msg


def test_model_alias_in_slash_commands():
    from cli.completer import SLASH_COMMANDS
    cmd_names = [cmd for cmd, _ in SLASH_COMMANDS]
    assert "/model" in cmd_names
    assert "/cmodel" in cmd_names


def test_fuzzy_slash_command_suggestions():
    from commands.aliases import suggest_slash_command, COMMON_SLASH_ALIASES

    # Exact or near typo matches
    assert suggest_slash_command("/histroy") == "/history"
    assert suggest_slash_command("/providr") == "/provider"
    assert suggest_slash_command("/consenus") == "/consensus"
    assert suggest_slash_command("/cmodl") in ["/cmodel", "/model"]

    # Aliases
    assert COMMON_SLASH_ALIASES["/q"] == "/quit"
    assert COMMON_SLASH_ALIASES["/cls"] == "/clear"
    assert COMMON_SLASH_ALIASES["/p"] == "/provider"
    assert COMMON_SLASH_ALIASES["/m"] == "/cmodel"


def test_resolve_file_mentions(tmp_path):
    # Setup files in tmp_path
    f1 = tmp_path / "hello.py"
    f1.write_text("print('hello world')", encoding="utf-8")

    sub = tmp_path / "subpkg"
    sub.mkdir()
    f2 = sub / "worker.py"
    f2.write_text("def work(): pass", encoding="utf-8")

    # 1. No mentions
    enriched, pinned, missing = file_manager.resolve_file_mentions("hello everyone", str(tmp_path))
    assert enriched == "hello everyone"
    assert pinned == []
    assert missing == []

    # 2. Existing file mentions
    query = "Check @hello.py and @worker.py please"
    enriched, pinned, missing = file_manager.resolve_file_mentions(query, str(tmp_path))
    assert len(pinned) == 2
    assert missing == []
    assert "print('hello world')" in enriched
    assert "def work(): pass" in enriched
    pinned_names = [p["name"] for p in pinned]
    assert "hello.py" in pinned_names
    assert "subpkg/worker.py" in pinned_names or "subpkg\\worker.py" in pinned_names

    # 3. Missing file mention
    query = "Look at @nonexistent.py"
    enriched, pinned, missing = file_manager.resolve_file_mentions(query, str(tmp_path))
    assert pinned == []
    assert "nonexistent.py" in missing


def test_at_file_completer(tmp_path):
    from klyro_cli import KlyroCompleter
    from prompt_toolkit.document import Document

    f1 = tmp_path / "service.py"
    f1.write_text("# code", encoding="utf-8")

    completer = KlyroCompleter(lambda: str(tmp_path))
    doc = Document("please inspect @serv", cursor_position=len("please inspect @serv"))
    completions = list(completer.get_completions(doc, None))
    assert len(completions) >= 1
    assert any(c.text == "@service.py" for c in completions)


def test_secret_redaction_guard():
    import security

    raw_prompt = (
        "Here is my config: openai_key = 'sk-proj-abc1234567890abcdef1234567890' and "
        "github = 'ghp_123456789012345678901234567890123456' and "
        "google = 'AIzaSyAbcdEfGhIjKlMnOpQrStUvWxYz0123456' and "
        "aws = 'AKIA1234567890ABCDEF' and "
        "db = 'postgres://admin:topsecretpass123@localhost:5432/db'\n"
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Y...\n-----END RSA PRIVATE KEY-----"
    )

    sanitized, detected = security.sanitize_outgoing_context(raw_prompt)

    # All secrets should be detected
    assert len(detected) >= 5
    # Raw secrets must NOT be present in sanitized output
    assert "sk-proj-abc1234567890abcdef1234567890" not in sanitized
    assert "ghp_123456789012345678901234567890123456" not in sanitized
    assert "AIzaSyAbcdEfGhIjKlMnOpQrStUvWxYz0123456" not in sanitized
    assert "AKIA1234567890ABCDEF" not in sanitized
    assert "topsecretpass123" not in sanitized
    assert "MIIEowIBAAKCAQEA0Y" not in sanitized

    # Redaction placeholders should be in place
    assert "[REDACTED_API_KEY]" in sanitized
    assert "[REDACTED_GITHUB_TOKEN]" in sanitized
    assert "[REDACTED_GOOGLE_KEY]" in sanitized
    assert "[REDACTED_AWS_ACCESS_KEY]" in sanitized
    assert "[REDACTED_DB_PASSWORD]" in sanitized
    assert "[REDACTED_PRIVATE_KEY]" in sanitized


def test_lockfile_and_large_file_mention_guard(tmp_path):
    # 1. Lockfile creation
    lock = tmp_path / "package-lock.json"
    lock.write_text('{"name": "test", "lockfileVersion": 3}', encoding="utf-8")

    # 2. Minified file creation
    min_js = tmp_path / "bundle.min.js"
    min_js.write_text("var a=1,b=2;", encoding="utf-8")

    # 3. Oversized file (>200 KB)
    large = tmp_path / "large_dataset.txt"
    large.write_text("A" * (250 * 1024), encoding="utf-8")

    # 4. Valid normal file
    valid = tmp_path / "main.py"
    valid.write_text("print('hello')", encoding="utf-8")

    # Test resolve_file_mentions with these files
    query = "Inspect @package-lock.json and @bundle.min.js and @large_dataset.txt and @main.py"
    enriched, pinned, missing = file_manager.resolve_file_mentions(query, str(tmp_path))

    # Only main.py should be pinned
    pinned_names = [p["name"] for p in pinned]
    assert "main.py" in pinned_names
    assert "package-lock.json" not in pinned_names
    assert "bundle.min.js" not in pinned_names
    assert "large_dataset.txt" not in pinned_names

    # Blocked files should be listed in missing with reason
    assert any("package-lock.json" in m for m in missing)
    assert any("bundle.min.js" in m for m in missing)
    assert any("large_dataset.txt" in m for m in missing)


def test_run_post_edit_diagnostics():
    import validations

    # 1. Valid Python
    ok, msg, diag = validations.run_post_edit_diagnostics("test.py", "x = 10\nprint(x)\n")
    assert ok is True
    assert "clean" in msg.lower()

    # 2. SyntaxError Python
    ok, msg, diag = validations.run_post_edit_diagnostics("test.py", "def foo(:\n    pass\n")
    assert ok is False
    assert "SyntaxError on line 1" in msg
    assert diag["errors"][0]["line"] == 1

    # 3. JSON Diagnostics
    ok, msg, _ = validations.run_post_edit_diagnostics("data.json", '{"key": "value"}')
    assert ok is True
    ok, msg, _ = validations.run_post_edit_diagnostics("data.json", '{"key": "value",}')
    assert ok is False
    assert "JSONDecodeError" in msg

    # 4. Delimiter Diagnostics
    ok, msg, _ = validations.run_post_edit_diagnostics("app.js", "function test() { if (true) { }")
    assert ok is False
    assert "Unclosed" in msg or "delimiter" in msg.lower()


def test_cmodel_restart_reload_alias(monkeypatch):
    from commands.command_handler import handle_slash_command
    from unittest.mock import MagicMock
    import provider_manager

    refreshed = []
    def mock_get_models(prov, force_refresh=False):
        if force_refresh:
            refreshed.append(prov)
        return [{"id": "model-1", "desc": "test model"}]

    monkeypatch.setattr(provider_manager, "get_provider_models", mock_get_models)

    mock_assistant = MagicMock()
    mock_assistant.provider = "groq"

    # Both restart and reload should trigger force_refresh
    handle_slash_command("/cmodel", "restart", ".", mock_assistant)
    assert "groq" in refreshed

    refreshed.clear()
    handle_slash_command("/cmodel", "reload", ".", mock_assistant)
    assert "groq" in refreshed


def test_apply_all_file_actions(tmp_path, monkeypatch):
    from apply_actions import parse_and_apply_actions

    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"

    response = (
        "```python:a.py\nprint('A')\n```\n"
        "```python:b.py\nprint('B')\n```\n"
    )

    prompts_asked = []
    def mock_input(prompt):
        prompts_asked.append(prompt)
        return "a"  # Type 'a' (all) on the first prompt

    monkeypatch.setattr("builtins.input", mock_input)

    parse_and_apply_actions(response, str(tmp_path), None)

    # Should only prompt once (for a.py with 'a'), and b.py is auto-applied
    assert len(prompts_asked) == 1
    assert f1.read_text(encoding="utf-8").strip() == "print('A')"
    assert f2.read_text(encoding="utf-8").strip() == "print('B')"


def test_incomplete_shell_command_skipped(capsys):
    from commands.command_handler import execute_ai_actions
    from unittest.mock import MagicMock

    response = '<!--ACTION:SHELL cmd="python -c"-->'
    execute_ai_actions(response, ".", MagicMock())
    captured = capsys.readouterr()
    assert "Incomplete shell command skipped" in captured.out


def test_switch_provider_uses_target_provider_model():
    from ai import AIAssistant

    assistant = AIAssistant()
    # Simulate being on openrouter with a free model
    assistant.provider = "openrouter"
    assistant.current_model = "z-ai/glm-5.2:free"

    # Switch to groq without specifying force_model
    assistant.switch_provider("groq")

    # Groq's model must NOT be openrouter's model
    assert assistant.provider == "groq"
    assert assistant.current_model != "z-ai/glm-5.2:free"
    assert "glm" not in assistant.current_model.lower()
    assert assistant.current_model  # must be a valid non-empty model identifier


def test_openai_sse_error_detection():
    from unittest.mock import MagicMock, patch
    from ai import OpenAICompatibleAssistant

    assistant = OpenAICompatibleAssistant("openrouter")
    assistant.api_key = "test-key"

    # Simulate SSE stream returning an error frame
    err_frame = b'data: {"error": {"message": "The model API is currently overloaded", "code": 503}}\n\n'
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = [err_frame]

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(Exception) as exc_info:
            list(assistant.tanya_stream("hi"))
        assert "overloaded" in str(exc_info.value).lower()


def test_openrouter_empty_response_triggers_fallback():
    from unittest.mock import MagicMock
    from ai import AIAssistant

    assistant = AIAssistant()
    assistant.provider = "openrouter"
    assistant.current_model = "openrouter/auto"

    # Simulate OpenRouter assistant returning empty generator (0 tokens)
    or_mock = MagicMock()
    or_mock.tanya_stream.return_value = iter([])
    assistant.openai_compatibles["openrouter"] = or_mock

    # Mock smart_router to return a fallback candidate
    assistant.smart_router = MagicMock()
    assistant.smart_router.get_fallback_candidates.return_value = [("gemini", "gemini-3.6-flash", "Gemini")]
    assistant.smart_router.temp_exclude_provider = MagicMock()

    # Mock active provider (Gemini) to return a greeting
    gemini_mock = MagicMock()
    gemini_mock.tanya_stream.return_value = iter(["Halo dari Gemini!"])
    assistant.gemini = gemini_mock

    # Collect stream from _openrouter_smart_stream
    output = "".join(list(assistant._openrouter_smart_stream("hi")))
    assert "Halo dari Gemini!" in output or "Auto-fallback" in output


def test_render_route_badge():
    from ai import AIAssistant
    from klyro_cli import render_route_badge

    assistant = AIAssistant()
    assistant.provider = "gemini"
    assistant.current_model = "gemini-3.6-flash"
    assistant.last_route_reason = "Code Task"
    assistant.routing_trail = []

    badge = render_route_badge(assistant)
    assert "Code Task" in badge
    assert "gemini-3.6-flash" in badge

    # With reroute trail
    assistant.routing_trail = [{"from": "MiniMax M3", "reason": "offline", "to": "Nemotron 3"}]
    badge_trail = render_route_badge(assistant)
    assert "rerouted" in badge_trail
    assert "MiniMax M3" in badge_trail


def test_router_command_simulation(capsys):
    from ai import AIAssistant
    from commands.command_handler import handle_slash_command

    assistant = AIAssistant()
    handle_slash_command("/router", "test buatkan fungsi sorting", ".", assistant)
    captured = capsys.readouterr()
    assert "Simulated Route Decision" in captured.out
    assert "Target Engine" in captured.out


def test_dirty_git_files_parsing(monkeypatch):
    import subprocess
    import validations

    fake_output = (
        " M validations.py\n"
        "M  staged_file.py\n"
        "?? untracked.txt\n"
        " D deleted.py\n"
        "R  old.py -> new.py\n"
        ' M "quoted path.py"\n'
    )
    class FakeResult:
        returncode = 0
        stdout = fake_output

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeResult())
    dirty = validations.get_dirty_git_files(".")
    assert "validations.py" in dirty
    assert "staged_file.py" in dirty
    assert "deleted.py" in dirty
    assert "old.py -> new.py" in dirty
    assert "quoted path.py" in dirty
    assert "untracked.txt" not in dirty
    # Verify no truncated first-character filenames
    assert "alidations.py" not in dirty
    assert "eleted.py" not in dirty


def test_check_dirty_git_guard(monkeypatch):
    import validations

    # Safe prompt (read-only) -> never warns
    assert validations.check_dirty_git_guard(".", "jelaskan kode ini") is True

    # Write prompt with dirty files: user chooses abort (n)
    monkeypatch.setattr(validations, "get_dirty_git_files", lambda folder: ["main.py"])
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert validations.check_dirty_git_guard(".", "refactor seluruh main.py") is False

    # User chooses proceed anyway (y)
    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert validations.check_dirty_git_guard(".", "refactor seluruh main.py") is True

    # User chooses auto-stash (s) - success
    monkeypatch.setattr("builtins.input", lambda prompt: "s")
    monkeypatch.setattr(validations, "run_auto_stash", lambda folder: (True, "Saved working directory"))
    assert validations.check_dirty_git_guard(".", "refactor seluruh main.py") is True

    # User chooses auto-stash (s) - failure
    monkeypatch.setattr(validations, "run_auto_stash", lambda folder: (False, "git lock error"))
    assert validations.check_dirty_git_guard(".", "refactor seluruh main.py") is False


def test_check_empty_input(capsys):
    import validations
    validations._consecutive_empty = 0

    # Non-empty real input
    assert validations.check_empty_input("hello world") is False
    assert validations._consecutive_empty == 0

    # Blank / noise inputs
    assert validations.check_empty_input("") is True
    assert validations.check_empty_input("   ") is True
    assert validations.check_empty_input("...") is True
    captured = capsys.readouterr()
    assert "Tip:" in captured.out and "/help" in captured.out
    assert validations._consecutive_empty == 0  # reset after threshold


def test_ping_ollama_and_cache(monkeypatch):
    import validations
    import urllib.request
    validations.reset_ollama_cache()

    class MockResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass

    requested_urls = []
    def mock_urlopen(req, timeout=1.5):
        requested_urls.append(req.full_url)
        return MockResp()

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    # URL without scheme should be prefixed with http://
    ok, msg = validations.ping_ollama("localhost:11434/v1")
    assert ok is True
    assert "Endpoint active" in msg
    assert requested_urls[-1] == "http://localhost:11434/v1/models"

    # Cached hit
    ok2, _ = validations.ping_ollama("localhost:11434/v1")
    assert ok2 is True
    assert len(requested_urls) == 1  # no extra network request

    validations.reset_ollama_cache()


def test_run_auto_stash_unit(monkeypatch):
    import subprocess
    import validations

    # Test success
    class FakeSuccess:
        returncode = 0
        stdout = "Saved working directory and index state WIP on main"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeSuccess())
    ok, msg = validations.run_auto_stash(".")
    assert ok is True
    assert "Saved working directory" in msg

    # Test failure
    class FakeFail:
        returncode = 1
        stdout = ""
        stderr = "fatal: not a git repository"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeFail())
    ok, msg = validations.run_auto_stash(".")
    assert ok is False
    assert "fatal" in msg


def test_check_git_conflict_markers():
    import validations

    # 1. Clean code
    clean_code = "def hello():\n    return 'clean'\n"
    has_c, line_no, marker = validations.check_git_conflict_markers(clean_code)
    assert has_c is False
    assert line_no == 0

    # 2. Code with conflict markers
    conflict_code = (
        "def compute():\n"
        "<<<<<<< HEAD\n"
        "    return 1\n"
        "=======\n"
        "    return 2\n"
        ">>>>>>> feature-branch\n"
    )
    has_c, line_no, marker = validations.check_git_conflict_markers(conflict_code)
    assert has_c is True
    assert line_no == 2
    assert marker == "<<<<<<< HEAD"

    # 3. Code with middle separator or base marker
    has_c, line_no, marker = validations.check_git_conflict_markers("line 1\n||||||| merged common ancestors\nline 3")
    assert has_c is True
    assert line_no == 2
    assert "|||||||" in marker


def test_post_edit_diagnostics_blocks_git_conflict_markers():
    import validations

    bad_py = "x = 1\n<<<<<<< HEAD\ny = 2\n=======\ny = 3\n>>>>>>> feat\n"
    ok, msg, diag = validations.run_post_edit_diagnostics("service.py", bad_py)
    assert ok is False
    assert "conflict marker" in msg.lower()
    assert diag["errors"][0]["type"] == "GitConflictMarker"
    assert diag["errors"][0]["line"] == 2

    # JS file with conflict
    bad_js = "function test() {\n<<<<<<< HEAD\n  return 1;\n=======\n  return 2;\n>>>>>>> main\n}"
    ok, msg, diag = validations.run_post_edit_diagnostics("index.js", bad_js)
    assert ok is False
    assert "conflict marker" in msg.lower()

    # Markdown doc file with tutorial conflict markers is not blocked
    tutorial_md = "# How to resolve merge conflicts\nExample:\n```\n<<<<<<< HEAD\nfoo\n=======\nbar\n>>>>>>> main\n```\n"
    ok, msg, _ = validations.run_post_edit_diagnostics("README.md", tutorial_md)
    assert ok is True


def test_file_manager_validasi_sintaks_blocks_conflict_markers():
    import file_manager

    code = "let a = 10;\n<<<<<<< HEAD\nlet b = 20;\n=======\nlet b = 30;\n>>>>>>> main"
    ok, msg = file_manager.validasi_sintaks("app.ts", code)
    assert ok is False
    assert "conflict marker" in msg.lower()


# ─────────────────────────────────────────────────────────────
# FEATURE 8: SECRET LEAK GUARD — AI FILE WRITE CHECK
# ─────────────────────────────────────────────────────────────

def test_security_check_secret_leak_detects_keys():
    """security.check_secret_leak should detect known hardcoded secret patterns."""
    import security

    # OpenAI key
    openai_code = 'api_key = "sk-proj-abcdefghijklmnopqrstuvwx12345678901234567890"'
    findings = security.check_secret_leak(openai_code)
    assert len(findings) > 0
    assert any(f["label"] in ("OpenAI / Provider API Key", "Generic sk- API Key") for f in findings)
    assert all("line" in f and "match" in f for f in findings)

    # GitHub token
    github_code = 'token = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456789012"'
    findings = security.check_secret_leak(github_code)
    assert any(f["label"] == "GitHub Token" for f in findings)

    # Google AI / Gemini key (AQ prefix)
    gemini_code = 'GEMINI_KEY = "AQabcdefghijklmnopqrstuvwxyz1234"'
    findings = security.check_secret_leak(gemini_code)
    assert any(f["label"] == "Google AI Key" for f in findings)

    # AWS access key
    aws_code = 'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"'
    findings = security.check_secret_leak(aws_code)
    assert any(f["label"] == "AWS Access Key ID" for f in findings)


def test_security_check_secret_leak_clean_code():
    """No findings on innocent code that has no hardcoded secrets."""
    import security

    clean = (
        "import os\n"
        "GEMINI_KEY = os.environ['GEMINI_KEY']\n"
        "OPENAI_KEY = os.getenv('OPENAI_KEY')\n"
        "# TODO: add API key here\n"
    )
    findings = security.check_secret_leak(clean)
    assert findings == []


def test_check_secret_in_file_write_skips_docs():
    """check_secret_in_file_write should skip .md / .txt files."""
    import validations

    # A markdown tutorial that mentions a fake secret pattern should not trigger
    md_content = (
        "# Setup Guide\n"
        "Set your key: `sk-proj-abcdefghijklmnopqrstuvwx12345678901234567890`\n"
    )
    findings = validations.check_secret_in_file_write("SETUP.md", md_content)
    assert findings == []  # .md is in SKIP_EXTENSIONS

    # Same content in a .py file SHOULD trigger
    findings_py = validations.check_secret_in_file_write("config.py", md_content)
    assert len(findings_py) > 0


def test_post_edit_diagnostics_surfaces_secret_warnings():
    """run_post_edit_diagnostics returns secret_warnings in details for clean Python."""
    import validations

    # Syntactically valid Python but hardcodes a GitHub token
    code = (
        "import requests\n"
        'GITHUB_TOKEN = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ123456789012"\n'
        "headers = {'Authorization': f'token {GITHUB_TOKEN}'}\n"
    )
    is_clean, msg, details = validations.run_post_edit_diagnostics("github_client.py", code)

    # Syntax is clean
    assert is_clean is True
    assert "python syntax" in msg.lower()

    # But secret_warnings should be populated
    secret_warnings = details.get("secret_warnings", [])
    assert len(secret_warnings) > 0
    assert any("GitHub Token" in w or "ghp_" in w.lower() or "line 2" in w for w in secret_warnings)
    assert any(".env" in w or "os.environ" in w for w in secret_warnings)


def test_post_edit_diagnostics_no_false_positives():
    """run_post_edit_diagnostics has no secret warnings on clean environment-loaded code."""
    import validations

    code = (
        "import os\n"
        "GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')\n"
        "OPENAI_KEY = os.getenv('OPENAI_API_KEY')\n"
    )
    is_clean, msg, details = validations.run_post_edit_diagnostics("client.py", code)
    assert is_clean is True
    assert details.get("secret_warnings", []) == []
