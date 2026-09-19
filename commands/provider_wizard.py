"""
commands/provider_wizard.py — Interactive wizard to configure AI providers, API keys, and models
"""

import sys
import provider_manager
from cli.spinner import prompt_secret
from cli.interactive_menu import interactive_select
from theme import (
    RESET, BOLD,
    FROST_CYAN, FROST_MINT, FROST_CORAL, FROST_AMBER,
    FROST_WHITE, FROST_GRAY, FROST_DARK, FROST_GHOST, FROST_INDIGO,
)


def run_provider_wizard(ai_assistant):
    """
    Interactive /provider wizard — Nordic Frost styled.
    Lets user pick a provider, enter API key, and select a model.
    """
    catalog = provider_manager.PROVIDER_CATALOG
    keys = list(catalog.keys())

    options_prov = []
    for pid in keys:
        p = catalog[pid]
        existing_key = provider_manager.get_api_key(pid)
        key_status = "configured" if existing_key else "no key"
        clean_tag = p["tag"].split(" • ")[-1] if " • " in p["tag"] else p["tag"]
        options_prov.append({
            "label": p["name"],
            "description": f"{key_status} | {clean_tag}"
        })

    cfg = provider_manager.load_config()
    default_provider = cfg.get("active_provider", "gemini")
    default_idx = keys.index(default_provider) if default_provider in keys else 0

    idx = interactive_select("Select AI Provider", options_prov, default_idx)
    if idx == -1:
        return

    provider_id = keys[idx]
    prov = catalog[provider_id]

    # ── Custom URL (only for custom provider) ─────────────────────────
    custom_url = None
    if provider_id == "custom":
        current_url = cfg.get("custom_base_url", "http://localhost:11434/v1")
        try:
            url_input = input(f"  {FROST_CYAN}Base URL{RESET} {FROST_DARK}[{current_url}]{RESET}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {FROST_DARK}Cancelled.{RESET}\n")
            return
        custom_url = url_input if url_input else current_url
        print(f"  {FROST_MINT}→{RESET} Base URL: {FROST_WHITE}{custom_url}{RESET}")

    # ── API Key ───────────────────────────────────────────────────────
    existing_key = provider_manager.get_api_key(provider_id)
    if existing_key and provider_id != "custom":
        fmt_ok, fmt_reason = provider_manager.validate_api_key_format(provider_id, existing_key)
        if not fmt_ok:
            print(f"  {FROST_AMBER}⚠️  Key tersimpan tidak valid atau dummy: {fmt_reason}{RESET}")
            print(f"  {FROST_DARK}Silakan masukkan API key baru yang valid.{RESET}")
            existing_key = ""
        else:
            suffix_len = min(4, len(existing_key))
            masked = "*" * min(len(existing_key) - suffix_len, 20) + existing_key[-suffix_len:] if len(existing_key) > suffix_len else "****"
            print(f"  {FROST_GRAY}Current key: {masked}{RESET}")
            try:
                keep = input(f"  {FROST_CYAN}Keep existing key? (Y/n):{RESET} ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print(f"\n  {FROST_DARK}Cancelled.{RESET}\n")
                return
            if keep in ("n", "no"):
                existing_key = ""

    while not existing_key:
        if provider_id == "custom":
            print(f"  {FROST_DARK}Local endpoint — no API key required. Press Enter to skip, or set one if your endpoint needs auth.{RESET}")
        placeholder = prov.get("key_placeholder", "")
        try:
            prompt_label = f"  {FROST_CYAN}Enter API Key{RESET} {FROST_DARK}(hidden input, e.g. {placeholder}):{RESET} "
            new_key = prompt_secret(prompt_label)
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {FROST_DARK}Cancelled.{RESET}\n")
            return
        if not new_key:
            if provider_id == "custom":
                print(f"  {FROST_DARK}No API key set — continuing without one (local endpoint).{RESET}")
                existing_key = ""
                break
            else:
                print(f"  {FROST_CORAL}✗{RESET} No API key provided. Setup cancelled.\n")
                return
        else:
            fmt_ok, fmt_reason = provider_manager.validate_api_key_format(provider_id, new_key)
            if not fmt_ok:
                print(f"  {FROST_AMBER}⚠️  Format key tidak sesuai: {fmt_reason}{RESET}")
                try:
                    retry = input(f"  {FROST_CYAN}Ketik ulang key? (Y/n):{RESET} ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    return
                if retry in ("n", "no"):
                    provider_manager.set_api_key(provider_id, new_key)
                    existing_key = new_key
                    print(f"  {FROST_DARK}Key tetap disimpan.{RESET}")
                    break
                continue
            else:
                provider_manager.set_api_key(provider_id, new_key)
                existing_key = new_key
                print(f"  {FROST_MINT}✓{RESET} API key valid & saved.")
                break

    # ── Model Selection ───────────────────────────────────────────────
    models = provider_manager.get_models_list(provider_id)
    model_ids = [m["id"] for m in models]
    current_model = cfg.get("active_models", {}).get(provider_id, prov["default_model"])

    options_model = []
    default_model_idx = 0
    for i, m in enumerate(models):
        m_id = m["id"]
        if m_id == current_model:
            default_model_idx = i
        options_model.append({
            "label": m_id,
            "description": m["desc"]
        })

    model_idx = interactive_select(f"Select Model for {prov['name']}", options_model, default_model_idx)
    if model_idx == -1:
        chosen_model = current_model
    else:
        chosen_model = model_ids[model_idx]

    # ── Apply & Switch ────────────────────────────────────────────────
    ok, msg = provider_manager.set_active_provider(provider_id, chosen_model, custom_url)
    if ok:
        ai_assistant.switch_provider(provider_id, chosen_model)
        prov_label = prov["name"]
        BAR = f"{FROST_DARK}│{RESET}"
        print(f"\n  {BAR}  {FROST_MINT}✓{RESET} {FROST_GRAY}Provider switched{RESET}")
        print(f"  {BAR}  {FROST_GHOST}engine{RESET}  {FROST_INDIGO}{prov_label}{RESET}")
        print(f"  {BAR}  {FROST_GHOST}model {RESET}  {FROST_GRAY}{chosen_model}{RESET}")

        # Live Handshake Probe
        if existing_key or provider_id == "custom":
            sys.stdout.write(f"  {BAR}  {FROST_CYAN}⠋{RESET} {FROST_GRAY}Verifying gateway connection...{RESET}\r")
            sys.stdout.flush()
            probe_ok, probe_msg, lat = provider_manager.probe_provider_key(provider_id, existing_key, custom_url=custom_url, timeout=3.5)
            if probe_ok:
                print(f"  {BAR}  {FROST_MINT}✔{RESET} {FROST_GRAY}Connection verified {FROST_DARK}({lat:.0f}ms){RESET}        ")
            else:
                print(f"  {BAR}  {FROST_CORAL}⚠️{RESET} {FROST_CORAL}{probe_msg}{RESET}        ")
                print(f"  {BAR}  {FROST_DARK}Tip: Periksa kembali API key via /provider jika query gagal.{RESET}")
        print()
    else:
        print(f"  {FROST_CORAL}✗{RESET} {msg}\n")
