"""
klyro_cli.py — Klyro Code CLI Entrypoint
Interactive agentic CLI coding assistant. This file is the slim entrypoint;
all heavy logic lives in the modular sub-packages:
  cli/        → Terminal UI, spinner, interactive menu, autocomplete
  commands/   → Slash command dispatcher, provider wizard, AI action executor
  core/       → Agent engine, tool registry, error handler
  tools/      → File search, symbol search, shell tools
"""

import os
import sys
import time

import provider_manager
import session_manager
import runner
import file_manager

# ── Windows UTF-8 & ANSI activation ──────────────────────────────────────────
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")

# ── Prompt Toolkit ────────────────────────────────────────────────────────────
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.formatted_text import ANSI
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False

# ── CLI sub-package (UI layer) ────────────────────────────────────────────────
from cli import (
    Spinner,
    CancellationMonitor,
    static_box_width,
    play_startup_animation,
    interactive_select,
    KlyroCompleter,
    _frost_style,
)

# ── Commands sub-package (slash commands + AI actions) ────────────────────────
from commands.command_handler import handle_slash_command, execute_ai_actions

# ── Core modules ──────────────────────────────────────────────────────────────
from config import MODEL_KECIL, GROQ_MODEL_CEPAT
from ai import AIAssistant
from errors import friendly
from consensus_engine import ConsensusEngine
from stream_view import CommentStripper, CodeBlockBuffer, ThinkingStreamHandler, StreamIndenter
import security

# ── Theme ─────────────────────────────────────────────────────────────────────
from theme import (
    RESET, BOLD,
    FROST_CYAN, FROST_ICE, FROST_MINT, FROST_INDIGO,
    FROST_CORAL, FROST_AMBER, FROST_WHITE, FROST_DARK, FROST_GRAY,
    get_git_branch, gradient_text, clip_line,
)
import shutil


def _clip(s: str) -> str:
    """Keep single-line UI elements to one physical row (no wrap-overlap)."""
    return clip_line(s, shutil.get_terminal_size(fallback=(80, 24)).columns - 1)


def render_route_badge(ai_assistant) -> str:
    route_info = getattr(ai_assistant, "last_route_reason", "Smart Router")
    if "]" in route_info:
        route_short = route_info.split("]")[0] + "]"
    elif len(route_info) > 35:
        route_short = route_info[:32] + "..."
    else:
        route_short = route_info

    model_name = ai_assistant.current_model.split("/")[-1] if "/" in ai_assistant.current_model else ai_assistant.current_model
    prov_name = provider_manager.PROVIDER_CATALOG.get(ai_assistant.provider, {}).get("name", ai_assistant.provider.upper())

    trail = getattr(ai_assistant, "routing_trail", [])
    if trail:
        hops = " -> ".join(
            f"{h['from']}{' (' + h['reason'] + ')' if h.get('reason') else ''}"
            for h in trail
        )
        return (
            f"  {FROST_CYAN}• {route_short}{RESET} {FROST_DARK}•{RESET} {FROST_WHITE}{BOLD}{prov_name}{RESET} {FROST_ICE}({model_name}){RESET}\n"
            f"    {FROST_DARK}-> rerouted: {FROST_GRAY}{hops}{RESET}\n\n"
        )
    return f"  {FROST_CYAN}• {route_short}{RESET} {FROST_DARK}•{RESET} {FROST_WHITE}{prov_name}{RESET} {FROST_ICE}({model_name}){RESET}\n\n"


def render_top_bar(folder_aktif: str, ai_assistant) -> str:
    cwd_display = os.path.basename(os.path.abspath(folder_aktif)) or folder_aktif.replace("\\", "/")
    git_branch = get_git_branch(folder_aktif)
    branch_part = f" {FROST_DARK}──{RESET} {FROST_MINT}git:{git_branch}{RESET}" if git_branch else ""

    prov_name = provider_manager.PROVIDER_CATALOG.get(ai_assistant.provider, {}).get("name", ai_assistant.provider.title())
    model_name = ai_assistant.current_model.split("/")[-1] if "/" in ai_assistant.current_model else ai_assistant.current_model
    is_router = getattr(ai_assistant, "smart_router_enabled", True)
    router_tag = f" {FROST_ICE}[auto]{RESET}" if is_router else ""
    has_key = bool(provider_manager.get_api_key(ai_assistant.provider)) if ai_assistant.provider != "custom" else True
    key_dot = f"{FROST_MINT}●{RESET}" if has_key else f"{FROST_AMBER}○{RESET}"

    return (
        f"  {FROST_CYAN}❄{RESET} {FROST_DARK}─{RESET} {FROST_WHITE}{BOLD}{cwd_display}{RESET}"
        f"{branch_part}"
        f" {FROST_DARK}──{RESET} {key_dot} {FROST_CYAN}{prov_name}{router_tag}{RESET} {FROST_DARK}({model_name}){RESET}"
    )


def render_micro_metrics(query_duration: float, full_response: str, ai_assistant) -> None:
    if not full_response:
        return
    est_tokens = max(1, len(full_response) // 4)
    speed_tps = est_tokens / query_duration if query_duration > 0.05 else 0.0
    model_name = ai_assistant.current_model.split("/")[-1] if "/" in ai_assistant.current_model else ai_assistant.current_model
    prov_name = provider_manager.PROVIDER_CATALOG.get(ai_assistant.provider, {}).get("name", ai_assistant.provider.title())

    tps_str = f"{speed_tps:.1f} tok/s" if speed_tps > 0 else "<0.1 tok/s"
    time_str = f"{query_duration:.1f}s"
    tok_str = f"~{est_tokens:,} tok"

    # Frost ribbon — 8-cell throughput meter (capped at 80 tok/s)
    filled = int(round(min(max(speed_tps, 0.0), 80.0) / 80.0 * 8))
    if filled > 0:
        ribbon = gradient_text("▰" * filled + "▱" * (8 - filled), (56, 189, 248), (129, 140, 248))
    else:
        ribbon = f"{FROST_DARK}▱▱▱▱▱▱▱▱{RESET}"
    tps_color = FROST_MINT if speed_tps >= 40 else FROST_CYAN

    print(
        f"  {ribbon} {FROST_DARK}•{RESET} {tps_color}{tps_str}{RESET} "
        f"{FROST_DARK}•{RESET} {FROST_ICE}{time_str}{RESET} "
        f"{FROST_DARK}•{RESET} {FROST_WHITE}{tok_str}{RESET} "
        f"{FROST_DARK}•{RESET} {FROST_GRAY}{prov_name} ({model_name}){RESET}\n"
    )


def main():
    ai_assistant = AIAssistant()
    folder_aktif = os.getcwd()

    konteks, file_dibaca, _ = file_manager.baca_semua_file(folder_aktif)
    ai_assistant.set_folder_context(
        folder_aktif, konteks,
        jumlah_file=len(file_dibaca),
        daftar_file=file_manager.list_daftar_file(folder_aktif),
    )
    ctx_warn = ai_assistant.get_context_preflight_warning()
    if ctx_warn:
        print(f"  {FROST_AMBER}⚠️  Context Notice: {ctx_warn}{RESET}")

    # ── Setup prompt session with autocomplete ────────────────────────────────
    _use_prompt_session = False
    prompt_session = None
    if PROMPT_TOOLKIT_AVAILABLE:
        try:
            prompt_session = PromptSession(
                completer=KlyroCompleter(lambda: folder_aktif),
                style=_frost_style,
                complete_while_typing=True,
                history=InMemoryHistory(),
            )
            _use_prompt_session = True
        except Exception:
            _use_prompt_session = False

    play_startup_animation(folder_aktif, ai_assistant)

    # ── Main REPL loop ────────────────────────────────────────────────────────
    while True:
        try:
            top_bar = render_top_bar(folder_aktif, ai_assistant)
            print(f"\n{_clip(top_bar)}")

            if _use_prompt_session:
                try:
                    ansi_prompt = ANSI("  \033[38;2;100;116;139m╰─\033[0m \033[38;2;56;189;248m\033[1m❯\033[0m ")
                    user_input = prompt_session.prompt(ansi_prompt).strip()
                except KeyboardInterrupt:
                    print(f"\n  {FROST_DARK}(Interrupted. Type /exit to quit){RESET}\n")
                    continue
                except EOFError:
                    print("\n  " + gradient_text("✦ Until next frost — goodbye ✦", (56, 189, 248), (129, 140, 248)) + "\n")
                    break
            else:
                user_input = input("  \033[38;2;100;116;139m╰─\033[0m \033[38;2;56;189;248m\033[1m❯\033[0m ").strip()

            import validations
            if validations.check_empty_input(user_input):
                continue

            # Guard: leftover input from a just-finished interactive program
            if runner.take_post_interactive_guard() and runner.looks_like_leftover_program_input(user_input):
                print(f"  {FROST_AMBER}That looks like input for the program that just exited.{RESET}")
                print(f"  {FROST_DARK}You are at the Klyro prompt, not inside the script.{RESET}")
                try:
                    send_ai = input(f"  {FROST_CYAN}Send {user_input!r} to the AI anyway?{RESET} {FROST_DARK}[y/N]{RESET} ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    send_ai = "n"
                    print()
                if send_ai not in ("y", "yes"):
                    print(f"  {FROST_DARK}Ignored. Re-run with /run or python file.py if needed.{RESET}\n")
                    continue

            # Route: bare shell commands (python foo.py, npm test, …)
            _shellish = runner.looks_like_direct_shell(user_input)
            runner._agent_dbg("H3", "klyro_cli.py:main_loop", "prompt routing", {
                "input_preview": user_input[:80],
                "starts_slash": user_input.startswith("/"),
                "starts_bang": user_input.startswith("!"),
                "looks_like_shell": _shellish,
                "route": "shell" if (_shellish or user_input.startswith("!")) else (
                    "slash" if user_input.startswith("/") else "ai"),
            })
            if _shellish:
                user_input = "!" + user_input

            # ── 1. Direct Shell Execution (!cmd) ─────────────────────────────
            if user_input.startswith("!"):
                raw_cmd = user_input[1:].strip()
                if raw_cmd:
                    is_danger, risk = security.check_command_safety(raw_cmd)
                    if is_danger:
                        print(f"\n  {FROST_CORAL}{BOLD}⚠️  SAFETY WARNING — DANGEROUS COMMAND:{RESET}")
                        print(f"  {FROST_WHITE}Command: {raw_cmd}{RESET}")
                        print(f"  {FROST_DARK}Risk   : {risk}{RESET}")
                        try:
                            allow = input(f"  {FROST_CORAL}Are you sure? (yes/N):{RESET} ").strip().lower()
                        except (KeyboardInterrupt, EOFError):
                            allow = "no"
                        if allow not in ["yes", "y"]:
                            print(f"  {FROST_DARK}Command cancelled for safety.{RESET}\n")
                            continue

                    raw_cmd = runner.wrap_script_command(raw_cmd, folder_aktif)
                    print(f"  {FROST_CYAN}⚡ Executing shell:{RESET} {FROST_WHITE}{raw_cmd}{RESET}")
                    print(f"  {FROST_DARK}Interactive — type program input here. Ctrl+C to stop.{RESET}")
                    res = runner.execute_script(raw_cmd, folder_aktif, interactive=True)
                    if res.get("stdout"):
                        print(res["stdout"])
                    if res.get("stderr"):
                        print(f"{FROST_CORAL}{res['stderr']}{RESET}")
                    bang_exit = res.get("exit_code")
                    print(f"  {'✓' if bang_exit == 0 else '✗'} {FROST_DARK}exit code {bang_exit}{RESET}")
                    print(f"  {FROST_AMBER}Back at Klyro — the program is no longer reading input.{RESET}\n")
                continue

            # ── 2. Slash Commands (/help, /model, /files, …) ─────────────────
            if user_input.startswith("/"):
                parts = user_input.split(" ", 1)
                cmd = parts[0]
                args = parts[1] if len(parts) > 1 else ""
                folder_aktif = handle_slash_command(cmd, args, folder_aktif, ai_assistant)
                continue

            # ── 3. AI Agentic Query (Real-Time Token Streaming) ───────────────
            import validations
            if not validations.check_ollama_preflight(ai_assistant):
                continue

            if not validations.check_dirty_git_guard(folder_aktif, user_input):
                print(f"  {FROST_DARK}Operation aborted.{RESET}\n")
                continue
            enriched_prompt, pinned_files, missing_files = file_manager.resolve_file_mentions(user_input, folder_aktif)
            if missing_files:
                missing_str = ", ".join(f"@{m}" for m in missing_files)
                print(f"  {FROST_AMBER}⚠️  File mention notice:{RESET} {missing_str}")
            if pinned_files:
                for pf in pinned_files:
                    trunc_note = f" {FROST_DARK}(truncated){RESET}" if pf.get("truncated") else ""
                    print(f"  {FROST_CYAN}📎 Pinned context:{RESET} {FROST_WHITE}@{pf['name']}{RESET} {FROST_ICE}({pf['size_kb']} KB){RESET}{trunc_note}")
                print()

            # Sanitize outgoing context to prevent accidental secret/credential leakage
            sanitized_prompt, redacted_secrets = security.sanitize_outgoing_context(enriched_prompt)
            if redacted_secrets:
                types_str = ", ".join(redacted_secrets)
                print(f"  {FROST_AMBER}🛡️  Secret Redaction:{RESET} {FROST_DARK}Protected sensitive credentials ({types_str}) before dispatch.{RESET}\n")
            prompt_to_send = sanitized_prompt
            max_attempts = 2
            for attempt in range(max_attempts):
                spinner = Spinner("Routing...")
                spinner.start()
                full_response_chunks = []
                first_chunk_received = False
                stream_color_on = False
                was_cancelled = False
                had_error = False
                t_query_start = time.time()

                cancel_monitor = CancellationMonitor()
                cancel_monitor.start()

                try:
                    stripper = CommentStripper()
                    thinker  = ThinkingStreamHandler(enabled=getattr(ai_assistant, "thinking_enabled", True))
                    code_buf = CodeBlockBuffer(live_counter=True)
                    indenter = StreamIndenter(indent="  ")
                    if getattr(ai_assistant, "consensus_mode", False):
                        stream = ConsensusEngine(ai_assistant).query(prompt_to_send)
                    else:
                        stream = ai_assistant.tanya_stream(prompt_to_send, on_status=spinner.update)
                    consensus_active = getattr(ai_assistant, "consensus_mode", False)

                    for chunk in stream:
                        if cancel_monitor.cancelled_by_esc:
                            raise KeyboardInterrupt("ESC pressed")

                        if not first_chunk_received:
                            spinner.stop()
                            if not consensus_active:
                                sys.stdout.write(_clip(render_route_badge(ai_assistant)))
                                sys.stdout.flush()
                            first_chunk_received = True

                        # Four-stage pipeline:
                        #   1. CommentStripper       — removes <!--ACTION...--> tags
                        #   2. ThinkingStreamHandler — formats <think>...</think> reasoning blocks
                        #   3. CodeBlockBuffer       — hides code until closing fence
                        #   4. StreamIndenter        — keeps clean 2-space left margin
                        stripped = stripper.feed(chunk)
                        thought  = thinker.feed(stripped)
                        visible  = code_buf.feed(thought)
                        indented = indenter.feed(visible)
                        if indented:
                            if not stream_color_on:
                                sys.stdout.write(FROST_WHITE)
                                stream_color_on = True
                            sys.stdout.write(indented)
                            sys.stdout.flush()
                        full_response_chunks.append(chunk)

                    # Flush stripper -> thinker -> code_buf -> indenter
                    stripped_flush = stripper.flush()
                    thought_flush  = thinker.feed(stripped_flush) if stripped_flush else ""
                    thought_final  = thinker.flush()
                    visible_flush  = code_buf.feed(thought_flush + thought_final)
                    last_flush     = code_buf.flush()
                    for part in (visible_flush, last_flush):
                        if part:
                            indented = indenter.feed(part)
                            if indented:
                                if not stream_color_on:
                                    sys.stdout.write(FROST_WHITE)
                                    stream_color_on = True
                                sys.stdout.write(indented)
                                sys.stdout.flush()
                    if stream_color_on:
                        sys.stdout.write(RESET)
                        sys.stdout.flush()
                    print()

                except KeyboardInterrupt:
                    was_cancelled = True
                    canc_think = thinker.cancel()
                    if canc_think:
                        sys.stdout.write(canc_think)
                        sys.stdout.flush()
                    canc_out = code_buf.cancel()
                    if canc_out:
                        sys.stdout.write(canc_out)
                        sys.stdout.flush()
                    if stream_color_on:
                        sys.stdout.write(RESET)
                        sys.stdout.flush()
                        stream_color_on = False
                    if not first_chunk_received:
                        spinner.stop()
                    reason = "dibatalkan dengan tombol ESC" if cancel_monitor.cancelled_by_esc else "dibatalkan pengguna (Ctrl+C)"
                    print(f"\n  {FROST_AMBER}⊘ Streaming {reason}.{RESET}\n")
                    break

                except Exception as e:
                    had_error = True
                    canc_think = thinker.cancel()
                    if canc_think:
                        sys.stdout.write(canc_think)
                        sys.stdout.flush()
                    canc_out = code_buf.cancel()
                    if canc_out:
                        sys.stdout.write(canc_out)
                        sys.stdout.flush()
                    if stream_color_on:
                        sys.stdout.write(RESET)
                        sys.stdout.flush()
                        stream_color_on = False
                    if not first_chunk_received:
                        spinner.stop()
                    print(f"\n  {FROST_CORAL}[Error] {friendly('Something went wrong', e)}{RESET}\n")

                    if attempt == 0 and not was_cancelled:
                        avail = provider_manager.get_available_providers()
                        # Exclude current provider and any temporarily excluded (rate limited / 429) providers
                        excluded = set()
                        if hasattr(ai_assistant, "smart_router") and hasattr(ai_assistant.smart_router, "_temp_excluded_providers"):
                            excluded = ai_assistant.smart_router._temp_excluded_providers
                        alts = [p for p in avail if p != ai_assistant.provider and p not in excluded]
                        if not alts:
                            alts = [p for p in avail if p != ai_assistant.provider]

                        if alts:
                            order = ["openrouter", "groq", "gemini", "cerebras", "deepseek", "mistral"]
                            best_alt = next((c for c in order if c in alts), alts[0])
                            alt_name = provider_manager.PROVIDER_CATALOG.get(best_alt, {}).get("name", best_alt.upper())

                            # Resolve the correct default/configured model for best_alt
                            cfg = provider_manager.load_config()
                            alt_model = (
                                cfg.get("active_models", {}).get(best_alt)
                                or provider_manager.PROVIDER_CATALOG.get(best_alt, {}).get("default_model", "")
                            )
                            # Ensure alt_model is not dead
                            try:
                                from core.model_discovery import get_dead_model_manager
                                if get_dead_model_manager().is_dead(best_alt, alt_model):
                                    alt_model = provider_manager.PROVIDER_CATALOG.get(best_alt, {}).get("default_model", "")
                            except Exception:
                                pass

                            try:
                                rec = input(f"  {FROST_CYAN}⚡ [Auto-Recovery] Switch ke {alt_name} ({alt_model})? (Y/n):{RESET} ").strip().lower()
                                if rec in ("", "y", "yes"):
                                    ai_assistant.switch_provider(best_alt, force_model=alt_model)
                                    provider_manager.set_active_provider(best_alt, alt_model)
                                    print(f"  {FROST_MINT}✓ Beralih ke {alt_name} ({alt_model}). Mengirim ulang...{RESET}\n")
                                    continue
                            except (KeyboardInterrupt, EOFError):
                                pass
                    break

                finally:
                    cancel_monitor.stop()
                    if not first_chunk_received:
                        spinner.stop()

                break

            # Record usage & execute AI actions only on clean success
            if not was_cancelled and not had_error and full_response_chunks:
                full_response = "".join(full_response_chunks)
                query_duration = time.time() - t_query_start
                render_micro_metrics(query_duration, full_response, ai_assistant)

                if full_response:
                    try:
                        sys_prompt_chars = ai_assistant.get_last_system_prompt_chars()
                    except Exception:
                        sys_prompt_chars = 0
                    session_manager.record_query_usage(
                        ai_assistant.provider,
                        ai_assistant.current_model,
                        user_input,
                        full_response,
                        query_duration,
                        extra_prompt_chars=sys_prompt_chars,
                    )
                    session_manager.save_interaction(
                        folder_aktif,
                        user_input,
                        full_response,
                        ai_assistant.provider,
                        ai_assistant.current_model,
                        query_duration,
                    )

                if full_response:
                    folder_aktif = execute_ai_actions(full_response, folder_aktif, ai_assistant)

        except KeyboardInterrupt:
            print(f"\n  {FROST_DARK}(Interrupted. Type /exit to quit){RESET}\n")
        except EOFError:
            print("\n  " + gradient_text("✦ Until next frost — goodbye ✦", (56, 189, 248), (129, 140, 248)) + "\n")
            break


if __name__ == "__main__":
    main()
