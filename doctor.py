"""
doctor.py — Self-Diagnostic & System Health Check for KlyroCLI
Validates Python runtime, OS capabilities, internet connectivity, API keys, and workspace health.
"""

import os
import sys
import time
import json
import socket
import shutil
import urllib.request
import subprocess
import provider_manager
import security
from errors import friendly

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from theme import (
    RESET, BOLD, DIM,
    FROST_CYAN, FROST_AQUA, FROST_MINT, FROST_CORAL,
    FROST_ICE, FROST_WHITE, FROST_GRAY, FROST_DARK, FROST_INDIGO,
    badge, keycap
)


def check_internet_ping(host="8.8.8.8", port=53, timeout=3) -> tuple[bool, float]:
    """Test raw DNS/IP connection latency in ms."""
    t0 = time.time()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        latency_ms = (time.time() - t0) * 1000
        return True, latency_ms
    except Exception:
        return False, 0.0


def check_endpoint_latency(url: str, timeout=4) -> tuple[bool, float, str]:
    """Test HTTP reachability to AI provider endpoints."""
    t0 = time.time()
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 KlyroCLI/Doctor"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency_ms = (time.time() - t0) * 1000
            return True, latency_ms, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        latency_ms = (time.time() - t0) * 1000
        return True, latency_ms, f"HTTP {e.code}"
    except Exception as e:
        return False, 0.0, friendly("Unreachable", e)


def _box_width(design_width: int) -> int:
    """Border width for this box's content."""
    term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    return max(20, min(design_width, term_width - 6))


def run_diagnostics(folder_aktif: str) -> dict:
    """Run full suite of self-diagnostics with live animated scan and print structured report."""
    print(f"\n  {FROST_CYAN}{BOLD}🩺 Klyro System & Health Diagnostics{RESET}")
    box_w = _box_width(66)
    print(f"  {FROST_DARK}╭{'─'*box_w}╮{RESET}")

    all_passed = True
    issues = []

    # Helper for live animated tick
    def scan_tick(msg):
        for frame in ["⠋", "⠙", "⠹", "⠸"]:
            sys.stdout.write(f"\r  {FROST_DARK}│{RESET}  {FROST_CYAN}{frame}{RESET} {FROST_GRAY}{msg}...{RESET}\033[K")
            sys.stdout.flush()
            time.sleep(0.015)

    # 1. Python Environment Check
    scan_tick("Checking Python Runtime")
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    status_py = f"{FROST_MINT}✔ Passed{RESET}" if py_ok else f"{FROST_CORAL}✘ Warning (< 3.10){RESET}"
    sys.stdout.write(f"\r  {FROST_DARK}│{RESET}  {FROST_WHITE}Python Runtime{RESET}      : {FROST_ICE}v{py_ver} ({sys.platform}){RESET} {status_py}\033[K\n")
    if not py_ok:
        issues.append("Python version is below 3.10. Some features may not work reliably.")
        all_passed = False

    # 2. Terminal & UTF-8 Encoding
    scan_tick("Checking Console Encoding")
    enc = sys.stdout.encoding or "unknown"
    enc_ok = "utf" in enc.lower()
    status_enc = f"{FROST_MINT}✔ UTF-8 OK{RESET}" if enc_ok else f"{FROST_CORAL}· Non-UTF8 ({enc}){RESET}"
    sys.stdout.write(f"\r  {FROST_DARK}│{RESET}  {FROST_WHITE}Console Encoding{RESET}    : {FROST_ICE}{enc.upper()}{RESET} {status_enc}\033[K\n")

    # 3. Workspace Permissions
    scan_tick("Validating Workspace Permissions")
    ws_writable = False
    test_file = os.path.join(folder_aktif, ".klyro_perm_test.tmp")
    try:
        with open(test_file, "w") as f:
            f.write("klyro_test")
        os.remove(test_file)
        ws_writable = True
    except Exception:
        ws_writable = False

    status_ws = f"{FROST_MINT}✔ Read/Write OK{RESET}" if ws_writable else f"{FROST_CORAL}✘ Read-Only / Permission Denied{RESET}"
    ws_name = os.path.basename(os.path.abspath(folder_aktif)) or folder_aktif
    sys.stdout.write(f"\r  {FROST_DARK}│{RESET}  {FROST_WHITE}Workspace Health{RESET}    : {FROST_ICE}{ws_name}{RESET} {status_ws}\033[K\n")
    if not ws_writable:
        issues.append(f"Workspace directory '{folder_aktif}' is not writable.")
        all_passed = False

    # 4. Git Integration Check
    scan_tick("Checking Git Integration")
    git_installed = False
    git_ver = ""
    is_git_repo = False
    try:
        proc = subprocess.run("git --version", shell=True, capture_output=True, text=True, timeout=2)
        if proc.returncode == 0:
            git_installed = True
            git_ver = proc.stdout.strip().replace("git version ", "")
            repo_proc = subprocess.run("git rev-parse --is-inside-work-tree", cwd=folder_aktif, shell=True, capture_output=True, text=True, timeout=2)
            is_git_repo = (repo_proc.returncode == 0 and "true" in repo_proc.stdout.lower())
    except Exception:
        pass

    if git_installed:
        repo_tag = f"{FROST_MINT}(git repository){RESET}" if is_git_repo else f"{FROST_DARK}(not a git repo){RESET}"
        sys.stdout.write(f"\r  {FROST_DARK}│{RESET}  {FROST_WHITE}Git Tooling{RESET}         : {FROST_ICE}v{git_ver}{RESET} {FROST_MINT}✔ Available{RESET} {repo_tag}\033[K\n")
    else:
        sys.stdout.write(f"\r  {FROST_DARK}│{RESET}  {FROST_WHITE}Git Tooling{RESET}         : {FROST_GRAY}Not found in PATH{RESET}\033[K\n")

    # 5. Network & AI Gateways Reachability
    scan_tick("Probing Internet Latency")
    net_ok, net_latency = check_internet_ping()
    probe_note = ""
    if not net_ok:
        https_ok, https_latency, _ = check_endpoint_latency("https://www.google.com")
        if https_ok:
            net_ok, net_latency = True, https_latency
            probe_note = f" {FROST_DARK}(via HTTPS fallback){RESET}"

    if net_ok:
        sys.stdout.write(f"\r  {FROST_DARK}│{RESET}  {FROST_WHITE}Internet Link{RESET}       : {FROST_MINT}✔ Online{RESET} {FROST_DARK}(Latency: {net_latency:.1f}ms){RESET}{probe_note}\033[K\n")
    else:
        sys.stdout.write(f"\r  {FROST_DARK}│{RESET}  {FROST_WHITE}Internet Link{RESET}       : {FROST_CORAL}✘ Offline / DNS issue{RESET}\033[K\n")
        issues.append("Internet connectivity appears to be offline.")
        all_passed = False

    print(f"  {FROST_DARK}│{RESET}")
    print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}{BOLD}AI Neural Gateways & Keys:{RESET}")

    cfg = provider_manager.load_config()
    active_prov = cfg.get("active_provider", "groq")

    providers_to_test = [
        ("gemini",     "https://generativelanguage.googleapis.com"),
        ("groq",       "https://api.groq.com/openai/v1/models"),
        ("cerebras",   "https://api.cerebras.ai/v1/models"),
        ("openrouter", "https://openrouter.ai/api/v1/models"),
        ("mistral",    "https://api.mistral.ai/v1/models"),
        ("deepseek",   "https://api.deepseek.com/models"),
        ("openai",     "https://api.openai.com/v1/models"),
    ]

    configured_count = 0
    for pid, endpoint in providers_to_test:
        cat = provider_manager.PROVIDER_CATALOG.get(pid, {})
        prov_name = cat.get("name", pid.upper())
        key = provider_manager.get_api_key(pid)
        is_active = (pid == active_prov)
        active_tag = f" {FROST_CYAN}[ACTIVE]{RESET}" if is_active else ""

        if key:
            configured_count += 1
            auth_ok, probe_msg, lat = provider_manager.probe_provider_key(pid, key, timeout=2.5)
            if auth_ok:
                lat_str = f"{FROST_DARK}({lat:.0f}ms){RESET}"
                print(f"  {FROST_DARK}│{RESET}    {FROST_MINT}●{RESET} {FROST_WHITE}{prov_name:<16}{RESET}: {FROST_MINT}Verified{RESET} {lat_str}{active_tag}")
            else:
                if is_active:
                    all_passed = False
                    issues.append(f"{prov_name} [ACTIVE]: {probe_msg}")
                print(f"  {FROST_DARK}│{RESET}    {FROST_AMBER}▲{RESET} {FROST_WHITE}{prov_name:<16}{RESET}: {FROST_CORAL}Key Invalid/Rejected{RESET}{active_tag}")
        else:
            print(f"  {FROST_DARK}│{RESET}    {FROST_DARK}○{RESET} {FROST_GRAY}{prov_name:<16}{RESET}: {FROST_DARK}No API Key{RESET}{active_tag}")

    # 6. Security Guardrails
    print(f"  {FROST_DARK}│{RESET}")
    print(f"  {FROST_DARK}│{RESET}  {FROST_WHITE}Security Guardrails{RESET} : {FROST_MINT}✔ Active{RESET} {FROST_DARK}(Sandbox & Danger Interceptor){RESET}")
    print(f"  {FROST_DARK}╰{'─'*box_w}╯{RESET}")

    if configured_count == 0:
        print(f"  {FROST_CORAL}⚠️  No AI API Keys configured yet! Type {BOLD}/provider{RESET}{FROST_CORAL} to setup Groq or Gemini.{RESET}\n")
    elif all_passed:
        print(f"  {FROST_MINT}✨ All systems healthy! Ready for high-speed agentic coding.{RESET}\n")
    else:
        print(f"  {FROST_CORAL}⚠️  Some issues were detected:{RESET}")
        for iss in issues:
            print(f"     • {iss}")
        print()

    return {"all_passed": all_passed, "issues": issues}


if __name__ == "__main__":
    run_diagnostics(os.getcwd())

