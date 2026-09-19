"""
commands/command_handler.py — Central slash command dispatcher and execution routines
"""

import os
import sys
import re
import subprocess
import shutil

import file_manager
import runner
import doctor
import session_manager
import provider_manager
import undo_manager
import security
from apply_actions import parse_and_apply_actions
from cli.spinner import Spinner, static_box_width, play_startup_animation
from cli.interactive_menu import interactive_select
from commands.aliases import COMMON_SLASH_ALIASES, suggest_slash_command
from commands.provider_wizard import run_provider_wizard
from errors import friendly
from theme import (
    RESET, BOLD,
    FROST_CYAN, FROST_AQUA, FROST_ICE, FROST_MINT, FROST_INDIGO,
    FROST_CORAL, FROST_AMBER, FROST_WHITE, FROST_GRAY,
    FROST_DARK, FROST_GHOST,
)

# Optional search tools registry
try:
    from core.tool_registry import ToolRegistry as _CoreToolRegistry
    from tools.search_tools import FileSearchTool, SymbolSearchTool
    _search_tools_registry = _CoreToolRegistry()
    _search_tools_registry.register(FileSearchTool())
    _search_tools_registry.register(SymbolSearchTool())
except Exception:
    _search_tools_registry = None


def handle_slash_command(cmd: str, args: str, folder_aktif: str, ai_assistant) -> str:
    """Handle all /slash commands with structured, categorized layout."""
    cmd = cmd.lower()
    if cmd in COMMON_SLASH_ALIASES:
        cmd = COMMON_SLASH_ALIASES[cmd]

    if cmd in ["/help", "/?"]:
        bw = static_box_width(64)
        print(f"\n  {FROST_CYAN}{BOLD}⚡ Klyro Command Palette{RESET}")

        # Section 1: AI & Neural
        print(f"  {FROST_DARK}╭─ {FROST_INDIGO}{BOLD}AI & Neural Engine{RESET} {FROST_DARK}{'─'*(bw-21)}╮{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/provider, /p{RESET}      {FROST_GRAY}Setup AI provider & API key (Gemini, Groq, etc){RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/cmodel, /m{RESET}        {FROST_GRAY}Switch active model for current provider{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/router [auto|off]{RESET}   {FROST_GRAY}Universal workload-based routing & auto-fallback{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/think [auto|on|off]{RESET} {FROST_GRAY}Visual thought process & deep reasoning stream{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/consensus{RESET}         {FROST_GRAY}Toggle multi-model parallel consensus mode{RESET}")
        print(f"  {FROST_DARK}╰{'─'*bw}╯{RESET}")

        # Section 2: Code & Project
        print(f"  {FROST_DARK}╭─ {FROST_AQUA}{BOLD}Code & Project Operations{RESET} {FROST_DARK}{'─'*(bw-28)}╮{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/files{RESET}             {FROST_GRAY}List all project files with sizes{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/tree{RESET}              {FROST_GRAY}Display interactive folder tree visualizer{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/find [glob]{RESET}       {FROST_GRAY}Find files by glob pattern, e.g. **/*.py{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/symbols <regex>{RESET}   {FROST_GRAY}Find functions/classes by name across project{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/diff{RESET}              {FROST_GRAY}Show git status and uncommitted diff{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/commit{RESET}            {FROST_GRAY}Auto-generate AI commit message & git commit{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/run [cmd]{RESET}         {FROST_GRAY}Smart run project script or background server{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/undo, /u{RESET}          {FROST_GRAY}Revert last AI file modifications{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/todo{RESET}              {FROST_GRAY}Scan workspace for TODOs & FIXMEs{RESET}")
        print(f"  {FROST_DARK}╰{'─'*bw}╯{RESET}")

        # Section 3: System & Diagnostics
        print(f"  {FROST_DARK}╭─ {FROST_MINT}{BOLD}System & Diagnostics{RESET} {FROST_DARK}{'─'*(bw-23)}╮{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/doctor, /doc{RESET}      {FROST_GRAY}Run comprehensive system & API health check{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/usage, /stat{RESET}      {FROST_GRAY}View tokens, speed (tok/s), latency & cost{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/history{RESET}           {FROST_GRAY}View or clear session conversation history{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/cd [path]{RESET}         {FROST_GRAY}Change active project directory{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/clear, /cls{RESET}       {FROST_GRAY}Clear screen & reset conversation{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}!command{RESET}           {FROST_GRAY}Execute shell command directly (e.g. !npm test){RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}/exit{RESET} {FROST_DARK}│{RESET} {FROST_CYAN}/q{RESET}          {FROST_GRAY}Exit Klyro Code{RESET}")
        print(f"  {FROST_DARK}╰{'─'*bw}╯{RESET}\n")
        return folder_aktif

    elif cmd in ["/doctor", "/doc"]:
        doctor.run_diagnostics(folder_aktif)
        return folder_aktif

    elif cmd in ["/router", "/route"]:
        from core.smart_router import get_smart_router, classify_workload
        router = get_smart_router()
        arg_str = (args or "").strip()
        arg_lower = arg_str.lower()
        subcmd = arg_lower.split()[0] if arg_lower else ""

        if subcmd in ["on", "auto", "enable", "aktif"]:
            ai_assistant.auto_route = True
            ai_assistant._user_locked_provider = False
            print(f"  {FROST_MINT}✓{RESET} Smart Workload Router {BOLD}ACTIVE{RESET} — AI models will dynamically route based on task complexity.\n")
            return folder_aktif

        elif subcmd in ["off", "manual", "disable", "nonaktif", "lock"]:
            ai_assistant.auto_route = False
            ai_assistant._user_locked_provider = True
            print(f"  {FROST_AMBER}ℹ{RESET} Smart Workload Router {BOLD}LOCKED{RESET} to current provider: {FROST_CYAN}{ai_assistant.provider.upper()}{RESET} ({ai_assistant.current_model})\n")
            return folder_aktif

        elif subcmd in ["reset", "clear"]:
            router.reset_exclusions()
            print(f"  {FROST_MINT}✓{RESET} Provider rate-limit exclusions reset. All providers eligible for routing.\n")
            return folder_aktif

        elif subcmd == "test":
            test_prompt = arg_str[4:].strip()
            if not test_prompt:
                print(f"  {FROST_AMBER}Usage:{RESET} {FROST_CYAN}/router test <pertanyaan/query>{RESET}\n")
                return folder_aktif
            ctx_len = len(ai_assistant.konteks or "")
            f_count = ai_assistant.jumlah_file or 0
            tier, reason = classify_workload(test_prompt, ctx_len, f_count)
            prov, model, route_reason, _ = router.route(test_prompt, ctx_len, f_count)
            prov_name = provider_manager.PROVIDER_CATALOG.get(prov, {}).get("name", prov.upper())

            bw = static_box_width(62)
            BAR = f"{FROST_DARK}│{RESET}"
            print(f"\n  {FROST_CYAN}{BOLD}⚡ Simulated Route Decision{RESET}")
            print(f"  {FROST_DARK}╭{'─'*bw}╮{RESET}")
            preview = test_prompt if len(test_prompt) <= 45 else test_prompt[:42] + "..."
            print(f"  {BAR}  {FROST_GHOST}Query       :{RESET} {FROST_WHITE}\"{preview}\"{RESET}")
            print(f"  {BAR}  {FROST_GHOST}Classified  :{RESET} {FROST_ICE}{BOLD}{tier.value}{RESET} {FROST_DARK}• {reason}{RESET}")
            print(f"  {BAR}  {FROST_GHOST}Target Engine:{RESET} {FROST_MINT}{BOLD}{prov_name}{RESET} {FROST_WHITE}({model}){RESET}")
            print(f"  {BAR}  {FROST_GHOST}Route Reason:{RESET} {FROST_GRAY}{route_reason}{RESET}")
            print(f"  {FROST_DARK}╰{'─'*bw}╯{RESET}\n")
            return folder_aktif

        # Default: Render Dashboard
        configured = router.get_configured_providers()
        excluded = getattr(router, "_temp_excluded_providers", set())
        avail = provider_manager.get_available_providers()

        status_tag = f"{FROST_MINT}● AUTO (Workload-Adaptive){RESET}" if ai_assistant.auto_route and not ai_assistant._user_locked_provider else f"{FROST_AMBER}🔒 LOCKED ({ai_assistant.provider.upper()}){RESET}"
        bw = static_box_width(64)
        BAR = f"{FROST_DARK}│{RESET}"

        print(f"\n  {FROST_CYAN}{BOLD}🌐 Universal Smart Router Dashboard{RESET}")
        print(f"  {FROST_DARK}╭{'─'*bw}╮{RESET}")
        print(f"  {BAR}  {FROST_GHOST}Router Mode   :{RESET} {status_tag}")
        print(f"  {BAR}  {FROST_GHOST}Active Model  :{RESET} {FROST_WHITE}{ai_assistant.provider.upper()}{RESET} {FROST_DARK}•{RESET} {FROST_ICE}{ai_assistant.current_model}{RESET}")
        print(f"  {BAR}  {FROST_GHOST}Last Decision :{RESET} {FROST_GRAY}{getattr(ai_assistant, 'last_route_reason', 'None')}{RESET}")
        print(f"  {BAR}")
        print(f"  {BAR}  {FROST_CYAN}{BOLD}Provider Fleet Health:{RESET}")
        for p_id in ["openrouter", "groq", "gemini", "cerebras", "deepseek", "mistral", "custom"]:
            if p_id not in provider_manager.PROVIDER_CATALOG:
                continue
            cat = provider_manager.PROVIDER_CATALOG[p_id]
            name = cat.get("name", p_id.upper())
            m = (
                provider_manager.load_config().get("active_models", {}).get(p_id)
                or cat.get("default_model", "")
            )
            if p_id in excluded:
                st = f"{FROST_AMBER}🟡 Rate-Limited{RESET}"
            elif p_id in avail:
                st = f"{FROST_MINT}🟢 Ready{RESET}"
            else:
                st = f"{FROST_DARK}⚪ No API Key{RESET}"
            m_short = m if len(m) <= 22 else m[:19] + "..."
            print(f"  {BAR}    {FROST_WHITE}{name:<16}{RESET} {st:<28} {FROST_DARK}{m_short}{RESET}")
        print(f"  {BAR}")
        print(f"  {BAR}  {FROST_CYAN}{BOLD}Workload Tier Routing Map:{RESET}")
        print(f"  {BAR}    {FROST_ICE}⚡ LIGHT    {RESET} {FROST_DARK}➔ Quick Q&A, chat, commands (speed priority){RESET}")
        print(f"  {BAR}    {FROST_MINT}💻 CODE     {RESET} {FROST_DARK}➔ Code creation, edit, debug, refactoring{RESET}")
        print(f"  {BAR}    {FROST_INDIGO}🧠 REASONING{RESET} {FROST_DARK}➔ Complex algorithms, math, architecture{RESET}")
        print(f"  {BAR}    {FROST_CORAL}📦 HEAVY    {RESET} {FROST_DARK}➔ Whole-project audit, multi-file migrations{RESET}")
        print(f"  {FROST_DARK}╰{'─'*bw}╯{RESET}")
        print(f"  {FROST_DARK}Commands:{RESET} {FROST_CYAN}/router auto{RESET} {FROST_DARK}│{RESET} {FROST_CYAN}/router off{RESET} {FROST_DARK}│{RESET} {FROST_CYAN}/router reset{RESET} {FROST_DARK}│{RESET} {FROST_CYAN}/router test <query>{RESET}\n")
        return folder_aktif

    elif cmd == "/consensus":
        ai_assistant.consensus_mode = not getattr(ai_assistant, "consensus_mode", False)
        if ai_assistant.consensus_mode:
            n_avail = len(provider_manager.get_available_providers())
            print(f"  {FROST_MINT}✓{RESET} Consensus mode {BOLD}ON{RESET} {FROST_DARK}({n_avail} provider(s) configured — queries will run in parallel){RESET}\n")
        else:
            print(f"  {FROST_DARK}Consensus mode OFF — back to single active model.{RESET}\n")
        return folder_aktif

    elif cmd in ["/think", "/thinking", "/thought"]:
        sub = args.strip().lower()
        if sub in ["on", "enable", "force"]:
            ai_assistant.thinking_enabled = True
            ai_assistant.force_thinking = True
            print(f"\n  {FROST_MINT}✓{RESET} {BOLD}Thinking Mode ON (Force Reasoning){RESET}")
            print(f"  {FROST_DARK}AI akan selalu menuliskan analisis dan alur arsitektur di dalam blok {FROST_CYAN}<think>{FROST_DARK} sebelum coding.{RESET}\n")
        elif sub in ["off", "disable"]:
            ai_assistant.thinking_enabled = False
            ai_assistant.force_thinking = False
            print(f"\n  {FROST_DARK}⊘ Thinking Mode OFF — Tampilan visual pemikiran dinonaktifkan.{RESET}\n")
        elif sub in ["auto", "passive", "smart", "default", "reset"]:
            ai_assistant.thinking_enabled = True
            ai_assistant.force_thinking = False
            print(f"\n  {FROST_MINT}✓{RESET} {BOLD}Thinking Mode: AUTO (Hemat Token - Passive Visualizer){RESET}")
            print(f"  {FROST_DARK}• 0 token tambahan pada model biasa.{RESET}")
            print(f"  {FROST_DARK}• Otomatis memvisualisasikan alur berpikir pada model reasoning (DeepSeek R1, QwQ, dll).{RESET}\n")
        else:
            # Status display
            is_enabled = getattr(ai_assistant, "thinking_enabled", True)
            is_forced = getattr(ai_assistant, "force_thinking", False)
            if not is_enabled:
                mode_str = f"{FROST_DARK}OFF (Disabled){RESET}"
            elif is_forced:
                mode_str = f"{FROST_CYAN}FORCE (Always Prompt Reasoning){RESET}"
            else:
                mode_str = f"{FROST_MINT}AUTO (Hemat Token - Passive Visualizer){RESET}"

            bw = static_box_width(58)
            BAR = f"{FROST_DARK}│{RESET}"
            print(f"\n  {FROST_DARK}╭─ {FROST_ICE}{BOLD}🧠 Visual Thinking Engine{RESET} {FROST_DARK}{'─'*(bw-27)}╮{RESET}")
            print(f"  {BAR}  {FROST_GRAY}Status Mode :{RESET} {mode_str}")
            print(f"  {BAR}  {FROST_GRAY}Overhead    :{RESET} {FROST_MINT}0 token (Zero extra cost on Auto){RESET}")
            print(f"  {BAR}  {FROST_GRAY}Supported   :{RESET} {FROST_WHITE}DeepSeek R1, QwQ, Nemotron, Groq Reasoning{RESET}")
            print(f"  {FROST_DARK}╰{'─'*bw}╯{RESET}")
            print(f"  {FROST_DARK}Commands:{RESET} {FROST_CYAN}/think auto{RESET} {FROST_DARK}│{RESET} {FROST_CYAN}/think on{RESET} {FROST_DARK}│{RESET} {FROST_CYAN}/think off{RESET}\n")
        return folder_aktif

    elif cmd in ["/clear", "/cls"]:
        play_startup_animation(folder_aktif, ai_assistant)
        return folder_aktif

    elif cmd in ["/cmodel", "/model", "/m", "/models"]:
        active_prov = ai_assistant.provider
        catalog_entry = provider_manager.PROVIDER_CATALOG.get(active_prov, {})

        # /cmodel refresh|sync|update|restart|reload — force live model fetch from provider API
        if args and args.strip().lower() in ("refresh", "sync", "update", "restart", "reload"):
            prov_name = catalog_entry.get("name", active_prov.upper())
            print(f"  {FROST_CYAN}🔄 Fetching live models from {prov_name}...{RESET}")
            try:
                fresh = provider_manager.get_provider_models(active_prov, force_refresh=True)
                if fresh:
                    print(f"  {FROST_MINT}✓{RESET} Refreshed {BOLD}{len(fresh)}{RESET} live model(s) for {prov_name}.\n")
                else:
                    print(f"  {FROST_AMBER}⚠{RESET} No live models returned — kept current catalog.\n")
            except Exception as e:
                print(f"  {FROST_CORAL}✗{RESET} Refresh failed: {e}\n")
            return folder_aktif

        models = provider_manager.get_models_list(active_prov)
        model_ids = [m["id"] for m in models]

        if not args:
            prov_name = catalog_entry.get("name", active_prov.upper())
            options_model = []
            default_idx = 0
            for i, m in enumerate(models):
                m_id = m["id"]
                if m_id == ai_assistant.current_model:
                    default_idx = i
                options_model.append({
                    "label": m_id,
                    "description": m["desc"]
                })

            chosen_idx = interactive_select(f"Switch {prov_name} Model", options_model, default_idx)
            if chosen_idx == -1:
                return folder_aktif
            target = model_ids[chosen_idx]

            ai_assistant.switch_provider(active_prov, target)
            provider_manager.set_active_provider(active_prov, target)
            print(f"  {FROST_MINT}✓{RESET} Model switched to {BOLD}{target}{RESET}\n")
        else:
            target = args.strip()
            if target.isdigit() and models:
                idx = int(target) - 1
                if 0 <= idx < len(model_ids):
                    target = model_ids[idx]
                else:
                    print(f"  {FROST_CORAL}✗{RESET} Number out of range. Use 1–{len(models)}.\n")
                    return folder_aktif
            elif model_ids and target not in model_ids:
                if active_prov == "custom":
                    pass
                else:
                    print(f"  {FROST_CORAL}✗{RESET} Unknown model '{target}' for {catalog_entry.get('name', active_prov.upper())}.")
                    print(f"  {FROST_DARK}Run {FROST_CYAN}/cmodel{FROST_DARK} with no argument to pick from the list.{RESET}\n")
                    return folder_aktif
            ai_assistant.switch_provider(active_prov, target)
            provider_manager.set_active_provider(active_prov, target)
            print(f"  {FROST_MINT}✓{RESET} Model switched to {BOLD}{target}{RESET}\n")
        return folder_aktif

    elif cmd in ["/provider", "/setup", "/p"]:
        run_provider_wizard(ai_assistant)
        return folder_aktif

    elif cmd in ["/usage", "/stat", "/stats"]:
        metrics = session_manager.get_usage_metrics()
        print(f"\n  {FROST_CYAN}{BOLD}Session Usage & Metrics{RESET}")
        print(f"  {FROST_DARK}┌{'─'*static_box_width(54)}┐{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_GRAY}Session Uptime :{RESET} {FROST_WHITE}{metrics['session_uptime']}{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_GRAY}Total Queries  :{RESET} {FROST_WHITE}{metrics['queries_count']} requests{RESET}")
        print(f"  {FROST_DARK}│{RESET}  {FROST_GRAY}Total Tokens   :{RESET} {FROST_ICE}~{metrics['total_tokens']:,} tok{RESET} {FROST_DARK}(Prompt: {metrics['prompt_tokens']:,} │ Resp: {metrics['response_tokens']:,}){RESET}")
        if metrics['queries_count'] > 0:
            print(f"  {FROST_DARK}│{RESET}  {FROST_GRAY}Avg Speed      :{RESET} {FROST_MINT}{metrics['avg_speed_tps']:.1f} tok/s{RESET} {FROST_DARK}(Avg Latency: {metrics['avg_latency_sec']:.2f}s){RESET}")

        cost_str = f"${metrics['estimated_cost_usd']:.4f}"
        cost_tag = f"{FROST_MINT}(Free Tier / No Cost){RESET}" if metrics['estimated_cost_usd'] == 0.0 else f"{FROST_CORAL}(Est. Paid Usage){RESET}"
        print(f"  {FROST_DARK}│{RESET}  {FROST_GRAY}Estimated Cost :{RESET} {FROST_WHITE}{cost_str}{RESET} {cost_tag}")

        if metrics['providers_used']:
            print(f"  {FROST_DARK}│{RESET}")
            print(f"  {FROST_DARK}│{RESET}  {FROST_CYAN}Engines Active in Session:{RESET}")
            for prov, pdata in metrics['providers_used'].items():
                p_tok = (pdata['p_chars'] + pdata['r_chars']) // 4
                print(f"  {FROST_DARK}│{RESET}    {FROST_INDIGO}•{RESET} {FROST_WHITE}{prov.upper():<10}{RESET} {FROST_GRAY}: {pdata['count']} queries (~{p_tok:,} tokens){RESET}")
        print(f"  {FROST_DARK}└{'─'*static_box_width(54)}┘{RESET}\n")
        return folder_aktif

    elif cmd == "/history":
        if args.strip().lower() in ["clear", "reset"]:
            session_manager.clear_history(folder_aktif)
            print(f"  {FROST_MINT}✓{RESET} Session history for this project cleared.\n")
            return folder_aktif

        history = session_manager.load_history(folder_aktif, limit=8)
        if not history:
            print(f"\n  {FROST_DARK}(No past interactions recorded for this project in .klyro/history.json){RESET}\n")
            return folder_aktif

        print(f"\n  {FROST_CYAN}{BOLD}Recent Session History ({len(history)} entries):{RESET}")
        print(f"  {FROST_DARK}┌{'─'*static_box_width(58)}┐{RESET}")
        for idx, entry in enumerate(history, 1):
            ts = entry.get("timestamp", "").split(" ")[-1]
            prov = entry.get("provider", "").upper()
            model = entry.get("model", "")
            prompt_preview = entry.get("prompt", "")
            if len(prompt_preview) > 55:
                prompt_preview = prompt_preview[:55] + "..."

            resp_preview = entry.get("response_summary", "")
            if len(resp_preview) > 60:
                resp_preview = resp_preview[:60] + "..."

            print(f"  {FROST_DARK}│{RESET}  {FROST_ICE}[{idx}]{RESET} {FROST_DARK}{ts}{RESET} {FROST_INDIGO}•{RESET} {FROST_WHITE}{prov}{RESET} {FROST_DARK}({model}){RESET}")
            print(f"  {FROST_DARK}│{RESET}      {FROST_CYAN}❯{RESET} {prompt_preview}")
            print(f"  {FROST_DARK}│{RESET}      {FROST_DARK}↳ {resp_preview}{RESET}")
            if idx < len(history):
                print(f"  {FROST_DARK}│{RESET}")
        print(f"  {FROST_DARK}└{'─'*static_box_width(58)}┘{RESET}")
        print(f"  {FROST_DARK}Type {FROST_CYAN}/history clear{FROST_DARK} to reset history.{RESET}\n")
        return folder_aktif

    elif cmd == "/files":
        files = file_manager.list_daftar_file(folder_aktif)
        print(f"\n  {FROST_CYAN}{BOLD}Project Files ({len(files)} total):{RESET}")
        for f in files:
            p = os.path.join(folder_aktif, f)
            size = os.path.getsize(p) if os.path.exists(p) else 0
            size_kb = f"{size / 1024:.1f} KB"
            print(f"    {FROST_INDIGO}•{RESET} {FROST_WHITE}{f:<35}{RESET} {FROST_DARK}{size_kb:>8}{RESET}")
        print()
        return folder_aktif

    elif cmd == "/tree":
        print(f"\n{file_manager.scan_struktur(folder_aktif)}\n")
        return folder_aktif

    elif cmd == "/run":
        subcmd = args.strip().lower() if args else ""
        if subcmd == "stop":
            res = runner.stop_server_process()
            if res.get("success"):
                print(f"  {FROST_MINT}✓{RESET} {res.get('message')}\n")
            else:
                print(f"  {FROST_CORAL}✗{RESET} Error: {res.get('error')}\n")
            return folder_aktif

        elif subcmd == "logs":
            status = runner.get_runner_status()
            if status.get("is_running"):
                print(f"\n  {FROST_CYAN}Active Background Server Logs:{RESET}")
            else:
                print(f"\n  {FROST_DARK}Background Server is NOT running. Showing last session logs:{RESET}")
            print(f"  {FROST_DARK}┌{'─'*static_box_width(64)}┐{RESET}")
            lines = status.get("logs", "").splitlines()
            for line in lines[-25:]:
                print(f"  {FROST_DARK}│{RESET}  {line}")
            print(f"  {FROST_DARK}└{'─'*static_box_width(64)}┘{RESET}\n")
            return folder_aktif

        elif subcmd == "status":
            status = runner.get_runner_status()
            if status.get("is_running"):
                print(f"\n  {FROST_CYAN}● Background Server Status:{RESET} {FROST_MINT}Running{RESET}\n")
            else:
                print(f"\n  {FROST_CYAN}● Background Server Status:{RESET} {FROST_DARK}Stopped{RESET}\n")
            return folder_aktif

        is_bg = False
        if args:
            cmd_to_run = args.strip()
            is_bg = runner.is_background_command(cmd_to_run)
            cmd_to_run = cmd_to_run.replace("&", "").replace("--bg", "").strip()
            cmd_to_run = runner.wrap_script_command(cmd_to_run, folder_aktif)
        else:
            info = runner.detect_project_runner(folder_aktif)
            cmd_to_run = info.get("command")
            is_bg = info.get("is_server", False)
            if not cmd_to_run:
                print(f"  {FROST_CORAL}✗{RESET} No default run command detected. Usage: {FROST_CYAN}/run <command>{RESET}")
                print(f"    {FROST_DARK}Example: {FROST_CYAN}/run Perbandingan.py{RESET}  or  {FROST_CYAN}/run python main.py{RESET}\n")
                return folder_aktif

        if is_bg:
            print(f"  {FROST_CYAN}⚡ Starting server in background:{RESET} {FROST_WHITE}{cmd_to_run}{RESET}")
            res = runner.start_server_process(cmd_to_run, folder_aktif)
            if res.get("success"):
                print(f"  {FROST_MINT}✓{RESET} {res.get('message')}")
                print(f"    {FROST_DARK}Management commands: {FROST_CYAN}/run logs{FROST_DARK} │ {FROST_CYAN}/run status{FROST_DARK} │ {FROST_CYAN}/run stop{RESET}\n")
            else:
                print(f"  {FROST_CORAL}✗{RESET} Failed to start background server: {res.get('error')}\n")
        else:
            print(f"  {FROST_CYAN}⚡ Running:{RESET} {FROST_WHITE}{cmd_to_run}{RESET}")
            print(f"  {FROST_DARK}Interactive — type program input here. Ctrl+C to stop.{RESET}")
            res = runner.execute_script(cmd_to_run, folder_aktif, interactive=True)
            if res.get("stdout"):
                print(res["stdout"])
            if res.get("stderr"):
                print(f"{FROST_CORAL}{res['stderr']}{RESET}")
            exit_code = res.get("exit_code")
            if exit_code == 0:
                print(f"\n  {FROST_MINT}✓{RESET} {FROST_DARK}Process finished (exit code {exit_code}, in {res.get('duration')}){RESET}")
            else:
                print(f"\n  {FROST_CORAL}✗{RESET} {FROST_DARK}Process failed (exit code {exit_code}, in {res.get('duration')}){RESET}")
            print(f"  {FROST_AMBER}Back at Klyro — the program is no longer reading input.{RESET}\n")

        return folder_aktif

    elif cmd == "/diff":
        try:
            res = subprocess.run("git diff", cwd=folder_aktif, shell=True, capture_output=True, text=True)
            if res.stdout:
                print(f"\n{res.stdout}\n")
            else:
                print(f"  {FROST_DARK}No uncommitted git changes.{RESET}\n")
        except Exception:
            print(f"  {FROST_CORAL}✗{RESET} Git command not available.\n")
        return folder_aktif

    elif cmd == "/commit":
        run_auto_commit(folder_aktif, ai_assistant)
        return folder_aktif

    elif cmd in ["/undo", "/u"]:
        ok, logs = undo_manager.apply_undo(folder_aktif)
        if ok:
            print(f"\n  {FROST_CYAN}{BOLD}Undo File Changes:{RESET}")
            print(f"  {FROST_DARK}┌{'─'*static_box_width(58)}┐{RESET}")
            for l in logs:
                print(f"  {FROST_DARK}│{RESET}  {FROST_MINT}↺{RESET} {FROST_WHITE}{l}{RESET}")
            print(f"  {FROST_DARK}└{'─'*static_box_width(58)}┘{RESET}")
            print(f"  {FROST_MINT}✓ Successfully reverted last file modifications.{RESET}\n")
            konteks, file_dibaca, _ = file_manager.baca_semua_file(folder_aktif)
            ai_assistant.set_folder_context(folder_aktif, konteks, jumlah_file=len(file_dibaca), daftar_file=file_manager.list_daftar_file(folder_aktif))
        else:
            print(f"\n  {FROST_DARK}↺ {logs[0]}{RESET}\n")
        return folder_aktif

    elif cmd == "/registry":
        import openrouter_registry as or_reg
        registry = or_reg.get_registry()
        force    = args.strip().lower() in ["refresh", "update", "reload"]

        if force:
            print(f"  {FROST_CYAN}⟳ Refreshing OpenRouter Model Registry...{RESET}")
            api_key = provider_manager.get_api_key("openrouter")
            registry.load(api_key, force_refresh=True)
            print(f"  {FROST_MINT}✓ Registry refreshed.{RESET}\n")
        else:
            registry.ensure_loaded(provider_manager.get_api_key("openrouter"))

        models = registry.all_models()
        pinned = [m for m in models if m.get("pinned")]
        dynamic = [m for m in models if not m.get("pinned")]

        print(f"\n  {FROST_CYAN}{BOLD}Klyro OpenRouter Model Registry ({len(models)} models){RESET}")
        print(f"  {FROST_DARK}┌{'─'*static_box_width(70)}┐{RESET}")

        print(f"  {FROST_DARK}│{RESET}  {FROST_INDIGO}{BOLD}Pinned (Research-validated):{RESET}")
        for m in pinned:
            cap    = m.get("capability", {})
            ctx_k  = f"{m.get('context', 0) // 1000}K"
            role   = m.get("role", "")
            score  = f"C{cap.get('coding',0)} R{cap.get('reasoning',0)} Ctx{cap.get('context',0)} T{cap.get('tool_use',0)} S{cap.get('speed',0)}"
            print(f"  {FROST_DARK}│{RESET}    {FROST_MINT}●{RESET} {FROST_WHITE}{m['id']:<45}{RESET} {FROST_DARK}{ctx_k:<6}{RESET} {FROST_ICE}[{role}]{RESET}")
            print(f"  {FROST_DARK}│{RESET}      {FROST_DARK}{score}{RESET}")

        if dynamic:
            print(f"  {FROST_DARK}│{RESET}")
            print(f"  {FROST_DARK}│{RESET}  {FROST_INDIGO}{BOLD}Dynamic (OpenRouter API):{RESET} {FROST_DARK}({len(dynamic)} models){RESET}")
            for m in dynamic[:8]:
                cap   = m.get("capability", {})
                ctx_k = f"{m.get('context', 0) // 1000}K"
                role  = m.get("role", "")
                print(f"  {FROST_DARK}│{RESET}    {FROST_CYAN}◌{RESET} {FROST_GRAY}{m['id']:<45}{RESET} {FROST_DARK}{ctx_k:<6} [{role}]{RESET}")
            if len(dynamic) > 8:
                print(f"  {FROST_DARK}│{RESET}    {FROST_DARK}... and {len(dynamic) - 8} more models{RESET}")

        print(f"  {FROST_DARK}└{'─'*static_box_width(70)}┘{RESET}")
        print(f"  {FROST_DARK}Type {FROST_CYAN}/registry refresh{FROST_DARK} to fetch latest from OpenRouter API.{RESET}\n")
        return folder_aktif

    elif cmd == "/todo":
        print(f"\n  {FROST_CYAN}{BOLD}Scanning workspace for TODOs & FIXMEs...{RESET}")
        todos = file_manager.scan_todos(folder_aktif)
        if not todos:
            print(f"  {FROST_MINT}✓{RESET} {FROST_GRAY}No TODOs or FIXMEs found. Workspace is clean!{RESET}\n")
            return folder_aktif

        print(f"  {FROST_CYAN}Found {len(todos)} items:{RESET}")
        print(f"  {FROST_DARK}┌{'─'*static_box_width(74)}┐{RESET}")
        for item in todos:
            f_display = item["file"]
            l_num = item["line"]
            text = item["text"]
            if len(f_display) > 25:
                f_display = "..." + f_display[-22:]
            if len(text) > 40:
                text = text[:37] + "..."

            left_part = f"{f_display}:{l_num}"
            print(f"  {FROST_DARK}│{RESET}  {FROST_WHITE}{left_part:<30}{RESET} {FROST_GRAY}→{RESET} {FROST_ICE}{text:<38}{RESET} {FROST_DARK}│{RESET}")
        print(f"  {FROST_DARK}└{'─'*static_box_width(74)}┘{RESET}\n")
        return folder_aktif

    elif cmd == "/find":
        if _search_tools_registry is None:
            print(f"  {FROST_CORAL}✗{RESET} Search tools unavailable (core/tools failed to load).\n")
            return folder_aktif

        pattern = args.strip() if args else "**/*"
        print(f"\n  {FROST_CYAN}{BOLD}Searching files:{RESET} {FROST_WHITE}{pattern}{RESET}")
        result = _search_tools_registry.execute("file_search", {"root_path": folder_aktif, "pattern": pattern})
        if not result.success:
            print(f"  {FROST_CORAL}✗{RESET} {result.error}\n")
            return folder_aktif

        matches = result.output
        if not matches:
            print(f"  {FROST_GRAY}No files matched.{RESET}\n")
            return folder_aktif

        shown = matches[:200]
        print(f"  {FROST_CYAN}Found {len(matches)} file(s):{RESET}")
        for m in shown:
            rel = os.path.relpath(m, folder_aktif)
            print(f"    {FROST_INDIGO}•{RESET} {FROST_WHITE}{rel}{RESET}")
        if len(matches) > len(shown):
            print(f"  {FROST_DARK}... and {len(matches) - len(shown)} more{RESET}")
        print()
        return folder_aktif

    elif cmd == "/symbols":
        if _search_tools_registry is None:
            print(f"  {FROST_CORAL}✗{RESET} Search tools unavailable (core/tools failed to load).\n")
            return folder_aktif

        if not args:
            print(f"  {FROST_CORAL}✗{RESET} Specify a symbol name/regex: {FROST_CYAN}/symbols <name_or_regex>{RESET}\n")
            return folder_aktif

        query = args.strip()
        print(f"\n  {FROST_CYAN}{BOLD}Searching symbols:{RESET} {FROST_WHITE}{query}{RESET}")
        result = _search_tools_registry.execute("symbol_search", {"root_path": folder_aktif, "query": query})
        if not result.success:
            print(f"  {FROST_CORAL}✗{RESET} {result.error}\n")
            return folder_aktif

        matches = result.output
        if not matches:
            print(f"  {FROST_GRAY}No symbols matched.{RESET}\n")
            return folder_aktif

        shown = matches[:100]
        print(f"  {FROST_CYAN}Found {len(matches)} symbol(s):{RESET}")
        for m in shown:
            rel = os.path.relpath(m["file"], folder_aktif)
            loc = f"{rel}:{m['line']}"
            print(f"    {FROST_INDIGO}•{RESET} {FROST_AMBER}{m['kind']:<8}{RESET} {FROST_WHITE}{m['symbol']:<28}{RESET} {FROST_DARK}{loc}{RESET}")
        if len(matches) > len(shown):
            print(f"  {FROST_DARK}... and {len(matches) - len(shown)} more{RESET}")
        print()
        return folder_aktif

    elif cmd == "/cd":
        if not args:
            print(f"  {FROST_CORAL}✗{RESET} Specify path: {FROST_CYAN}/cd <folder_path>{RESET}")
            return folder_aktif
        target = runner.resolve_cd_path(args, folder_aktif)
        if target and os.path.isdir(target):
            folder_aktif = target
            konteks, file_dibaca, _ = file_manager.baca_semua_file(folder_aktif)
            ai_assistant.set_folder_context(folder_aktif, konteks, jumlah_file=len(file_dibaca), daftar_file=file_manager.list_daftar_file(folder_aktif))
            ws_name = os.path.basename(folder_aktif) or folder_aktif
            file_count = len(file_dibaca)
            print(f"\n  {FROST_DARK}┌{'─'*static_box_width(54)}┐{RESET}")
            print(f"  {FROST_DARK}│{RESET}  {FROST_MINT}✓ Workspace switched{RESET}")
            print(f"  {FROST_DARK}│{RESET}  {FROST_GRAY}Name   :{RESET} {FROST_WHITE}{BOLD}{ws_name}{RESET}")
            print(f"  {FROST_DARK}│{RESET}  {FROST_GRAY}Path   :{RESET} {FROST_ICE}{folder_aktif}{RESET}")
            print(f"  {FROST_DARK}│{RESET}  {FROST_GRAY}Files  :{RESET} {FROST_CYAN}{file_count} files scanned into context{RESET}")
            print(f"  {FROST_DARK}└{'─'*static_box_width(54)}┘{RESET}\n")
        else:
            print(f"  {FROST_CORAL}✗{RESET} Directory not found: {args}")
            hints = runner.suggest_cd_paths(args, folder_aktif)
            if hints:
                print(f"  {FROST_DARK}Did you mean:{RESET}")
                for h in hints:
                    print(f"    {FROST_CYAN}{h}{RESET}")
            else:
                print(f"  {FROST_DARK}Tried workspace, home, and Documents — no close match.{RESET}")
        return folder_aktif

    elif cmd in ["/exit", "/quit"]:
        print(f"\n  {FROST_CYAN}Goodbye! Thanks for using Klyro Code.{RESET}\n")
        sys.exit(0)

    else:
        suggestion = suggest_slash_command(cmd)
        if suggestion:
            print(f"  {FROST_CORAL}✗{RESET} Unknown command {FROST_CYAN}{cmd}{RESET}. Did you mean {BOLD}{FROST_MINT}{suggestion}{RESET}?\n  {FROST_DARK}Type {FROST_CYAN}/help{FROST_DARK} for all available commands.{RESET}\n")
        else:
            print(f"  {FROST_CORAL}✗{RESET} Unknown command {FROST_CYAN}{cmd}{RESET}. Type {FROST_CYAN}/help{RESET} for options.\n")
        return folder_aktif


def run_auto_commit(folder_aktif: str, ai_assistant):
    """Generate conventional commit message using AI and execute git commit."""
    try:
        repo_check = subprocess.run(
            "git rev-parse --is-inside-work-tree",
            cwd=folder_aktif, shell=True, capture_output=True, text=True
        )
        if repo_check.returncode != 0:
            print(f"\n  {FROST_CORAL}✗{RESET} Current folder is not a Git repository.\n")
            return
    except Exception as e:
        print(f"\n  {FROST_CORAL}✗{RESET} Git command failed: {e}\n")
        return

    status_proc = subprocess.run(
        "git status --short",
        cwd=folder_aktif, shell=True, capture_output=True, text=True
    )
    status_output = status_proc.stdout.strip()
    if not status_output:
        print(f"\n  {FROST_DARK}No uncommitted changes in Git repository.{RESET}\n")
        return

    lines = status_output.splitlines()
    print(f"\n  {FROST_CYAN}{BOLD}Modified & Untracked Files ({len(lines)} total):{RESET}")
    for l in lines[:12]:
        print(f"    {FROST_INDIGO}•{RESET} {FROST_WHITE}{l}{RESET}")
    if len(lines) > 12:
        print(f"    {FROST_DARK}... and {len(lines) - 12} more files{RESET}")

    diff_proc = subprocess.run(
        "git diff HEAD",
        cwd=folder_aktif, shell=True, capture_output=True, text=True
    )
    diff_text = diff_proc.stdout.strip()
    if not diff_text:
        diff_proc = subprocess.run(
            "git diff",
            cwd=folder_aktif, shell=True, capture_output=True, text=True
        )
        diff_text = diff_proc.stdout.strip()

    if len(diff_text) > 10000:
        diff_text = diff_text[:10000] + "\n...[diff truncated for length]..."

    prompt = (
        "Generate a concise, standard conventional commit message (e.g. feat: ..., fix: ..., refactor: ..., docs: ...) "
        "accurately summarizing these git changes.\n\n"
        f"Git Status:\n{status_output}\n\n"
        f"Git Diff:\n{diff_text if diff_text else '[Untracked / Added files]'}\n\n"
        "RULES: Output ONLY the commit message in 1 or 2 lines maximum. Do not include markdown code blocks, quotes, or conversational filler."
    )

    spinner = Spinner("Analyzing git changes & drafting commit message...")
    spinner.start()
    try:
        raw_msg = ai_assistant.tanya(prompt).strip()
    finally:
        spinner.stop()

    commit_msg = raw_msg.strip("`'\"\n ")
    if "\n" in commit_msg:
        c_lines = [cl.strip() for cl in commit_msg.splitlines() if cl.strip()]
        commit_msg = "\n".join(c_lines[:2])

    print(f"\n  {FROST_CYAN}{BOLD}Suggested Commit Message:{RESET}")
    print(f"  {FROST_DARK}┌{'─'*static_box_width(64)}┐{RESET}")
    for cl in commit_msg.splitlines():
        print(f"  {FROST_DARK}│{RESET}  {FROST_MINT}{BOLD}{cl}{RESET}")
    print(f"  {FROST_DARK}└{'─'*static_box_width(64)}┘{RESET}")

    try:
        action = input(f"  {FROST_CYAN}Commit with this message?{RESET} {FROST_DARK}[Y/n/edit]:{RESET} ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print(f"\n  {FROST_DARK}Commit cancelled.{RESET}\n")
        return

    if action in ["", "y", "yes"]:
        final_msg = commit_msg
    elif action in ["e", "edit"]:
        try:
            custom = input(f"  {FROST_CYAN}Enter custom commit message:{RESET} ").strip()
            if not custom:
                print(f"  {FROST_DARK}Commit cancelled (empty message).{RESET}\n")
                return
            final_msg = custom
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {FROST_DARK}Commit cancelled.{RESET}\n")
            return
    else:
        print(f"  {FROST_DARK}Commit cancelled.{RESET}\n")
        return

    add_res = subprocess.run(
        "git add -A",
        cwd=folder_aktif, shell=True, capture_output=True, text=True
    )
    if add_res.returncode != 0:
        print(f"  {FROST_CORAL}✗{RESET} Failed to stage files: {add_res.stderr}\n")
        return

    commit_res = subprocess.run(
        ["git", "commit", "-m", final_msg],
        cwd=folder_aktif, capture_output=True, text=True
    )
    if commit_res.returncode == 0:
        print(f"\n  {FROST_MINT}✓ Successfully committed:{RESET} {FROST_WHITE}{final_msg}{RESET}\n")
    else:
        print(f"  {FROST_CORAL}✗{RESET} Commit failed: {commit_res.stderr or commit_res.stdout}\n")


def execute_ai_actions(response_text: str, folder_aktif: str, ai_assistant) -> str:
    """
    Parse dan eksekusi ACTION tags yang dihasilkan AI secara otomatis.
    Format: <!--ACTION:TYPE key="value" -->
    """
    did_mutate = False
    delete_all_confirmed = False

    action_pattern = re.compile(r'<!--\s*ACTION:(\w+)\s+(.*?)\s*-->', re.IGNORECASE)
    attr_pattern = re.compile(r'(\w+)="([^"]*?)"')
    recorded_ops = []

    for match in action_pattern.finditer(response_text):
        action_type = match.group(1).upper()
        attrs_raw   = match.group(2)
        attrs       = dict(attr_pattern.findall(attrs_raw))

        try:
            if action_type == "DELETE":
                path_rel = attrs.get("path", "")
                targets = [p.strip() for p in path_rel.replace(";", ",").split(",") if p.strip()]
                valid_targets = []
                for rel in targets:
                    target = os.path.join(folder_aktif, rel)
                    if not file_manager.is_safe_path(folder_aktif, target, rel_path=rel):
                        print(f"  {FROST_CORAL}✗{RESET} Akses ditolak: {rel}")
                        continue
                    if os.path.isfile(target) or os.path.isdir(target):
                        valid_targets.append((rel, target))
                    else:
                        print(f"  {FROST_DARK}⊘ File/folder not found: {rel}{RESET}")

                if not valid_targets:
                    continue

                if not delete_all_confirmed:
                    print(f"\n  {FROST_CORAL}{BOLD}⚠️  AI wants to DELETE:{RESET}")
                    for rel, _ in valid_targets:
                        kind = "folder" if os.path.isdir(os.path.join(folder_aktif, rel)) else "file"
                        print(f"  {FROST_WHITE}  • {rel} ({kind}){RESET}")
                    try:
                        allow = input(f"  {FROST_CORAL}Confirm deletion? (yes/N/a [all]):{RESET} ").strip().lower()
                    except (KeyboardInterrupt, EOFError):
                        allow = "no"
                    if allow in ("a", "all"):
                        delete_all_confirmed = True
                    elif allow not in ["yes", "y"]:
                        print(f"  {FROST_DARK}Deletion cancelled.{RESET}\n")
                        continue

                for rel, target in valid_targets:
                    if os.path.isfile(target):
                        old_code, _ = file_manager.baca_satu_file(target)
                        os.remove(target)
                        print(f"  {FROST_MINT}✓{RESET} Deleted {BOLD}{rel}{RESET}")
                        recorded_ops.append({"type": "delete", "path": target, "old_content": old_code})
                        did_mutate = True
                    elif os.path.isdir(target):
                        for root, _, files in os.walk(target):
                            for file in files:
                                fpath = os.path.join(root, file)
                                old_code, _ = file_manager.baca_satu_file(fpath)
                                if old_code is not None:
                                    recorded_ops.append({"type": "delete", "path": fpath, "old_content": old_code})
                        shutil.rmtree(target)
                        print(f"  {FROST_MINT}✓{RESET} Deleted folder {BOLD}{rel}{RESET}")
                        did_mutate = True

            elif action_type == "RENAME":
                src_rel = attrs.get("from", "")
                dst_rel = attrs.get("to", "")
                src = os.path.join(folder_aktif, src_rel)
                dst = os.path.join(folder_aktif, dst_rel)
                if not file_manager.is_safe_path(folder_aktif, src, rel_path=src_rel) or not file_manager.is_safe_path(folder_aktif, dst, rel_path=dst_rel):
                    print(f"  {FROST_CORAL}✗{RESET} Akses ditolak (path traversal): {src_rel} → {dst_rel}")
                    continue
                if not os.path.exists(src):
                    print(f"  {FROST_CORAL}✗{RESET} Source not found: {src_rel}")
                    continue

                overwrite_warning = f"  {FROST_CORAL}(will overwrite existing {dst_rel}){RESET}" if os.path.exists(dst) else ""
                print(f"\n  {FROST_CYAN}AI wants to rename:{RESET} {FROST_WHITE}{src_rel}{RESET} → {FROST_WHITE}{dst_rel}{RESET}{overwrite_warning}")
                try:
                    allow = input(f"  {FROST_CYAN}Confirm? (Y/n):{RESET} ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    allow = "no"
                if allow not in ["", "y", "yes"]:
                    print(f"  {FROST_DARK}Rename cancelled.{RESET}\n")
                    continue

                os.rename(src, dst)
                print(f"  {FROST_MINT}✓{RESET} Renamed {BOLD}{src_rel}{RESET} → {BOLD}{dst_rel}{RESET}")
                recorded_ops.append({"type": "rename", "src": src, "dst": dst})
                did_mutate = True

            elif action_type == "MKDIR":
                path_rel = attrs.get("path", "")
                dirpath = os.path.join(folder_aktif, path_rel)
                if not file_manager.is_safe_path(folder_aktif, dirpath, rel_path=path_rel):
                    print(f"  {FROST_CORAL}✗{RESET} Akses ditolak (path traversal): {path_rel}")
                    continue
                os.makedirs(dirpath, exist_ok=True)
                print(f"  {FROST_MINT}✓{RESET} Created directory {BOLD}{path_rel}{RESET}")
                did_mutate = True

            elif action_type == "SHELL":
                cmd = attrs.get("cmd", "").strip()
                if cmd:
                    # Incomplete command check (e.g. python -c without argument)
                    if cmd in ("python -c", "python -c \"\"", "python -c ''", "python -m", "node -e", "node -e \"\"", "node -e ''") or (cmd.startswith("python -c") and len(cmd.split()) == 2):
                        print(f"\n  {FROST_AMBER}⚠ Incomplete shell command skipped (missing script argument): {cmd}{RESET}\n")
                        continue

                    is_interactive, interactive_reason = security.check_interactive_command(cmd)
                    if is_interactive:
                        print(f"\n  {FROST_CORAL}{BOLD}⚠️  BLOCKED — INTERACTIVE COMMAND:{RESET}")
                        print(f"  {FROST_DARK}Command : {cmd}{RESET}")
                        print(f"  {FROST_CORAL}Reason  : {interactive_reason}{RESET}")
                        print(f"  {FROST_DARK}Interactive commands hang automated agent execution. Denied.{RESET}\n")
                        continue

                    is_danger, risk = security.check_command_safety(cmd)
                    if is_danger:
                        print(f"\n  {FROST_CORAL}{BOLD}⚠️  SAFETY WARNING — DANGEROUS AI ACTION:{RESET}")
                        print(f"  {FROST_WHITE}Command: {cmd}{RESET}")
                        print(f"  {FROST_DARK}Risk   : {risk}{RESET}")
                        prompt_text = f"  {FROST_CORAL}Allow execution? (yes/N):{RESET} "
                        default_deny = True
                    else:
                        print(f"\n  {FROST_CYAN}AI wants to run a shell command:{RESET}")
                        print(f"  {FROST_WHITE}{cmd}{RESET}")
                        prompt_text = f"  {FROST_CYAN}Allow execution? (Y/n):{RESET} "
                        default_deny = False

                    try:
                        allow = input(prompt_text).strip().lower()
                    except (KeyboardInterrupt, EOFError):
                        allow = "no" if default_deny else ""

                    allowed = (allow in ["yes", "y"]) if default_deny else (allow in ["", "y", "yes"])
                    if not allowed:
                        print(f"  {FROST_DARK}Shell action cancelled.{RESET}\n")
                        continue

                    cmd = runner.wrap_script_command(cmd, folder_aktif)
                    interactive = runner.command_needs_tty(cmd)
                    print(f"  {FROST_CYAN}⚡{RESET} Running: {FROST_WHITE}{cmd}{RESET}")
                    if interactive:
                        print(f"  {FROST_DARK}Interactive — type program input here. Ctrl+C to stop.{RESET}")
                    res = runner.execute_script(cmd, folder_aktif, interactive=interactive)
                    if res.get("stdout"):
                        print(res["stdout"])
                    if res.get("stderr"):
                        print(f"{FROST_CORAL}{res['stderr']}{RESET}")
                    shell_exit_code = res.get("exit_code")
                    if shell_exit_code == 0:
                        print(f"  {FROST_MINT}✓{RESET} {FROST_DARK}exit code {shell_exit_code}{RESET}")
                    else:
                        print(f"  {FROST_CORAL}✗{RESET} {FROST_DARK}exit code {shell_exit_code}{RESET}")
                    if interactive:
                        print(f"  {FROST_AMBER}Back at Klyro — the program is no longer reading input.{RESET}")

        except Exception as e:
            print(f"  {FROST_CORAL}✗{RESET} {friendly(f'Action failed ({action_type})', e)}")

    if recorded_ops:
        undo_manager.record_transaction(folder_aktif, recorded_ops)

    if did_mutate and ai_assistant is not None:
        konteks, file_dibaca, _ = file_manager.baca_semua_file(folder_aktif)
        ai_assistant.set_folder_context(folder_aktif, konteks, jumlah_file=len(file_dibaca), daftar_file=file_manager.list_daftar_file(folder_aktif))

    parse_and_apply_actions(response_text, folder_aktif, ai_assistant)
    return folder_aktif
