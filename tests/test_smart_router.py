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

    # 2. Code query -> Groq Flagship 120B or OpenRouter
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


def test_smart_router_copilot_auto_routing_groq(monkeypatch):
    """Test Copilot Auto Routing for Groq: small model for chat, large for coding, reasoning for logic."""
    import provider_manager
    router = SmartRouter()
    monkeypatch.setattr(
        router,
        "get_configured_providers",
        lambda: {"groq": "mock_groq_key"},
    )
    # Configure groq's active model as 'auto'
    cfg = provider_manager.load_config()
    cfg["active_models"]["groq"] = "auto"
    monkeypatch.setattr(provider_manager, "load_config", lambda: cfg)

    # 1. Casual Chat / Light -> should pick lightweight 8B/20B model
    prov, model, reason, tier = router.route("halo apa kabar, bisa bantu saya hari ini?", manual_override="groq")
    assert prov == "groq"
    assert tier == WorkloadTier.LIGHT
    assert model in ["llama-3.1-8b-instant", "openai/gpt-oss-20b", "groq/compound-mini"]
    assert "Auto" in reason

    # 2. Coding / Debugging -> should pick large flagship 70B/120B model
    prov, model, reason, tier = router.route("buatkan fungsi binary search di python dan tulis unit test nya", manual_override="groq")
    assert prov == "groq"
    assert tier == WorkloadTier.CODE
    assert model in ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "groq/compound"]
    assert "Auto" in reason

    # 3. Deep Reasoning / Architecture -> should pick reasoning model
    prov, model, reason, tier = router.route("analisis mendalam akar penyebab race condition pada worker thread", manual_override="groq")
    assert prov == "groq"
    assert tier == WorkloadTier.REASONING
    assert model in ["deepseek-r1-distill-llama-70b", "qwen/qwen3.8-27b", "qwen-qwq-32b"]
    assert "Auto" in reason


def test_smart_router_copilot_auto_routing_gemini(monkeypatch):
    """Test Copilot Auto Routing for Gemini: fast flash for chat, 2.5-flash for coding, pro for logic."""
    import provider_manager
    router = SmartRouter()
    monkeypatch.setattr(
        router,
        "get_configured_providers",
        lambda: {"gemini": "mock_gemini_key"},
    )
    cfg = provider_manager.load_config()
    cfg["active_models"]["gemini"] = "auto"
    monkeypatch.setattr(provider_manager, "load_config", lambda: cfg)

    # 1. Casual chat -> lightweight flash
    prov, model, reason, tier = router.route("selamat pagi, apa kabar?", manual_override="gemini")
    assert prov == "gemini"
    assert tier == WorkloadTier.LIGHT
    assert model in ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
    assert "Auto" in reason

    # 2. Coding -> flagship coding flash (3.6-flash)
    prov, model, reason, tier = router.route("buatkan controller FastAPI dan model Pydantic", manual_override="gemini")
    assert prov == "gemini"
    assert tier == WorkloadTier.CODE
    assert model in ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview"]
    assert "Auto" in reason

    # 3. Reasoning -> Pro model
    prov, model, reason, tier = router.route("pembuktian matematis dan kompleksitas big-o", manual_override="gemini")
    assert prov == "gemini"
    assert tier == WorkloadTier.REASONING
    assert model in ["gemini-3.1-pro-preview", "gemini-4-argon", "gemini-3.6-flash", "gemini-3.8-flash"]
    assert "Auto" in reason


def test_cmodel_auto_slash_commands():
    """Verify /cmodel auto, /cmodel 1, and /cmodel copilot activate Auto Routing."""
    from commands.command_handler import handle_slash_command
    from unittest.mock import MagicMock

    assistant = MagicMock()
    assistant.provider = "groq"

    # 1. /cmodel auto
    handle_slash_command("/cmodel", "auto", ".", assistant)
    assistant.set_model.assert_called_with("auto")

    # 2. /cmodel 1 (Option 1 in menu)
    assistant.reset_mock()
    handle_slash_command("/cmodel", "1", ".", assistant)
    assistant.set_model.assert_called_with("auto")

    # 3. /cmodel copilot
    assistant.reset_mock()
    handle_slash_command("/cmodel", "copilot", ".", assistant)
    assistant.set_model.assert_called_with("auto")

    # 4. /cmodel auto all
    assistant.reset_mock()
    handle_slash_command("/cmodel", "auto all", ".", assistant)
    assistant.set_model.assert_called_with("auto", lock_provider=False)


def test_ai_assistant_auto_routing_state_sync(monkeypatch):
    """Verify that AIAssistant syncs current_model, target_model, and user locking properly."""
    from ai import AIAssistant
    import provider_manager

    # Mock provider manager to use Groq with key
    monkeypatch.setattr(provider_manager, "get_api_key", lambda p: "mock_key")
    ai = AIAssistant()
    ai.provider = "gemini"

    # Set model to auto
    ai.set_model("auto")
    assert ai.auto_route is True
    assert ai.target_model == "auto"
    assert ai._user_locked_provider is True
    assert ai.current_model != "auto"  # Must be an actual model ID
    assert "Auto" in ai.model_info

    # In-provider routing for Gemini: code -> gemini-3.6-flash
    prov, model, reason = ai._route_for_task("buat fungsi login dan refactor controller")
    assert prov == "gemini"
    assert "gemini-3.6-flash" in model or "gemini-3.8-flash" in model or "3." in model

    # When lock_provider=False (auto all), provider locking is released
    ai.set_model("auto", lock_provider=False)
    assert ai._user_locked_provider is False


def test_intra_provider_fallback_when_model_fails(monkeypatch):
    """When a model is unavailable on the locked provider, it must fallback within the same provider first."""
    from ai import AIAssistant, ModelUnavailable
    import provider_manager
    from unittest.mock import MagicMock

    monkeypatch.setattr(provider_manager, "get_api_key", lambda p: "mock_key")
    mock_dead_mgr = MagicMock()
    mock_dead_mgr.is_dead.return_value = False
    monkeypatch.setattr("core.model_discovery.get_dead_model_manager", lambda: mock_dead_mgr)

    ai = AIAssistant()
    ai.folder_aktif = "test_dir"
    ai.switch_provider("gemini", force_model="auto")
    assert ai.provider == "gemini"
    assert ai._user_locked_provider is True

    # Simulate first model failing with ModelUnavailable, second model succeeding
    attempt = 0
    def mock_tanya_stream(prompt):
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            raise ModelUnavailable("gemini", "gemini-2.5-flash-lite", "Model 404")
        yield "Response from backup Gemini model"

    mock_gemini = MagicMock()
    mock_gemini.tanya_stream = mock_tanya_stream
    mock_gemini.init_chat = MagicMock(return_value=(True, "ok"))
    ai.gemini = mock_gemini

    chunks = list(ai.tanya_stream("Halo"))
    response = "".join(chunks)

    # Must stay on Gemini!
    assert ai.provider == "gemini"
    assert "Response from backup Gemini model" in response
    assert len(ai.routing_trail) > 0
    assert "tidak tersedia" in ai.routing_trail[0]["reason"]


def test_user_locked_provider_does_not_cross_providers(monkeypatch):
    """When all models in a locked provider fail, Klyro must not silently jump to another provider."""
    from ai import AIAssistant, ModelUnavailable
    import provider_manager
    from unittest.mock import MagicMock

    monkeypatch.setattr(provider_manager, "get_api_key", lambda p: "mock_key")
    mock_dead_mgr = MagicMock()
    monkeypatch.setattr("core.model_discovery.get_dead_model_manager", lambda: mock_dead_mgr)

    ai = AIAssistant()
    ai.folder_aktif = "test_dir"
    ai.switch_provider("gemini", force_model="gemini-2.5-flash")
    ai._user_locked_provider = True

    # Exhaust all intra-provider candidates
    monkeypatch.setattr(ai.smart_router, "get_intra_provider_candidates", lambda prov, tier, exclude_models: [])

    mock_gemini = MagicMock()
    def fail_stream(prompt):
        raise ModelUnavailable("gemini", "gemini-2.5-flash", "All models 404")
    mock_gemini.tanya_stream = fail_stream
    ai.gemini = mock_gemini

    chunks = list(ai.tanya_stream("Halo"))
    response = "".join(chunks)

    # Must not switch provider!
    assert ai.provider == "gemini"
    assert "terkunci" in response or "tidak tersedia" in response



