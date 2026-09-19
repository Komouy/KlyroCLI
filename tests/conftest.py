"""
conftest.py — Global Pytest Fixtures & Test Sandboxing for KlyroCLI
Ensures tests run in an isolated sandbox and never modify real user configuration or cache.
"""
import os
import shutil
import pytest
import provider_manager

@pytest.fixture(autouse=True)
def isolate_klyro_environment(tmp_path, monkeypatch):
    """
    Autouse fixture that redirects provider_manager.CONFIG_FILE to a temporary sandbox
    file for every test, preserving user's actual klyro_config.json from test side-effects.
    """
    sandbox_config = str(tmp_path / "sandbox_klyro_config.json")
    
    # If a real config exists, copy it as a starting template so tests have sensible defaults
    real_config = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "klyro_config.json")
    if os.path.exists(real_config):
        try:
            shutil.copyfile(real_config, sandbox_config)
        except Exception:
            pass

    monkeypatch.setattr(provider_manager, "CONFIG_FILE", sandbox_config)
    yield
