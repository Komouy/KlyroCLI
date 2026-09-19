"""
runner.py — Smart Project Runner for Klyro Studio (Optimized & Robust)
Mendukung eksekusi otomatis & kustom berbagai jenis proyek:
- Python (Script, Django, Flask, FastAPI)
- Node / React / Vite / Next.js (package.json scripts)
- Laravel / PHP (artisan serve, built-in)
- HTML Live Web Preview
- Custom Shell Commands
"""

import os
import sys
import json
import re
import time
import shlex
import subprocess
import threading
from errors import friendly, DEBUG

# Interpreters used when the user (or AI) passes a script path without one.
# On Windows, a bare `foo.py` is opened with the file association (often VS Code).
_SCRIPT_INTERPRETERS = {
    ".py":  [sys.executable, "-u"],
    ".pyw": [sys.executable, "-u"],
    ".js":  ["node"],
    ".mjs": ["node"],
    ".cjs": ["node"],
    ".rb":  ["ruby"],
    ".php": ["php"],
    ".pl":  ["perl"],
}

_KNOWN_INTERPRETERS = {
    "python", "python3", "pythonw", "py", "node", "nodejs",
    "php", "ruby", "perl", "lua", "dotnet", "java", "javac",
}

_DIRECT_SHELL_HEADS = {
    "python", "python3", "pythonw", "py", "node", "nodejs", "npm", "npx",
    "yarn", "pnpm", "pip", "pip3", "git", "cargo", "php", "go", "java",
    "javac", "ruby", "perl", "pytest", "dotnet", "mvn", "gradle", "make",
    "docker", "composer", "uv", "poetry", "ruff", "mypy", "black",
}

_SKIP_SCAN_DIRS = {
    ".git", ".klyro", "venv", ".venv", "node_modules", "__pycache__",
    ".idea", ".vscode", "dist", "build", "env",
}

_SERVER_PATTERNS = (
    "npm run dev", "npm start", "yarn dev", "yarn start",
    "pnpm dev", "pnpm start", "bun run dev",
    "php artisan serve", "manage.py runserver",
    "flask run", "uvicorn ", "npx vite",
    "cargo watch", "dotnet watch",
)

_INTERACTIVE_HEADS = {
    "python", "python3", "pythonw", "py", "node", "nodejs",
    "php", "ruby", "perl", "lua", "irb", "ghci",
}

# Global state untuk proses yang sedang berjalan
running_process = None
process_lock = threading.Lock()
process_logs = []

def _agent_dbg(hypothesis_id, location, message, data=None):
    """Hypothesis log — silent unless KLYRO_DEBUG=1. Never writes in normal use."""
    if not DEBUG:
        return
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug-klyro.log")
        with open(path, "a", encoding="utf-8") as _f:
            _f.write(json.dumps({
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "data": data or {},
                "timestamp": int(time.time() * 1000),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _get_execution_env() -> dict:
    """Mengembalikan environment variable yang optimal untuk streaming real-time."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["FORCE_COLOR"] = "1"
    env["NODE_ENV"] = "development"
    return env


def _quote_cmd(parts: list) -> str:
    """Join argv into a shell command string that is safe on this OS."""
    if sys.platform == "win32":
        return subprocess.list2cmdline(parts)
    return " ".join(shlex.quote(p) for p in parts)


def _split_command(command: str) -> list:
    command = (command or "").strip()
    if not command:
        return []
    try:
        return shlex.split(command, posix=(os.name != "nt"))
    except ValueError:
        return command.split()


def resolve_existing_file(cwd: str, path: str):
    """Resolve a file path relative to cwd, case-insensitive on Windows."""
    if not path:
        return None
    candidate = path if os.path.isabs(path) else os.path.join(cwd or "", path)
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    parent = os.path.dirname(candidate)
    base = os.path.basename(candidate)
    if parent and os.path.isdir(parent):
        try:
            for name in os.listdir(parent):
                if name.lower() == base.lower() and os.path.isfile(os.path.join(parent, name)):
                    return os.path.abspath(os.path.join(parent, name))
        except OSError:
            pass
    return None


def wrap_script_command(command: str, cwd: str) -> str:
    """
    If the first token is a source file without an interpreter, prefix one.
    Prevents Windows from opening .py/.js files in the associated editor.
    """
    tokens = _split_command(command)
    if not tokens:
        return command

    head = tokens[0]
    head_base = os.path.basename(head).lower()
    head_stem = os.path.splitext(head_base)[0]
    # Already an interpreter / launcher (python.exe, node.cmd, …)
    if head_stem in _KNOWN_INTERPRETERS or head_base.startswith("python"):
        return command

    resolved = resolve_existing_file(cwd, head)
    if not resolved:
        ext = os.path.splitext(head)[1].lower()
        if ext in _SCRIPT_INTERPRETERS:
            prefix = _SCRIPT_INTERPRETERS[ext]
            return _quote_cmd(prefix + [head] + tokens[1:])
        return command

    ext = os.path.splitext(resolved)[1].lower()
    prefix = _SCRIPT_INTERPRETERS.get(ext)
    if not prefix:
        return command
    return _quote_cmd(prefix + [resolved] + tokens[1:])


def is_background_command(command: str) -> bool:
    """True only for real long-running servers — not filenames containing 'start'."""
    raw = (command or "").strip()
    if not raw:
        return False
    if raw.endswith("&"):
        return True
    tokens = raw.replace("=", " ").split()
    if "--bg" in tokens:
        return True
    lower = raw.lower()
    return any(pat in lower for pat in _SERVER_PATTERNS)


def command_needs_tty(command: str) -> bool:
    """Scripts and interpreters that typically call input() / read stdin."""
    tokens = _split_command(command)
    if not tokens:
        return False
    head = os.path.basename(tokens[0]).lower()
    stem = os.path.splitext(head)[0]
    if head in _INTERACTIVE_HEADS or stem in _INTERACTIVE_HEADS or head.startswith("python"):
        return True
    ext = os.path.splitext(head)[1].lower()
    if ext in _SCRIPT_INTERPRETERS:
        return True
    return False


def looks_like_direct_shell(user_input: str) -> bool:
    """
    Detect when the user typed a real CLI command at the Klyro prompt
    (e.g. `python Perbandingan.py`) instead of a natural-language request.
    """
    text = (user_input or "").strip()
    if not text or text.startswith("/") or text.startswith("!"):
        return False
    tokens = _split_command(text)
    if not tokens:
        return False
    head = os.path.basename(tokens[0]).lower()
    ext = os.path.splitext(head)[1].lower()
    if ext in _SCRIPT_INTERPRETERS or ext in {".exe", ".bat", ".cmd", ".ps1"}:
        return True
    if head in _DIRECT_SHELL_HEADS and len(tokens) >= 2:
        return True
    return False


def resolve_cd_path(raw: str, folder_aktif: str = None):
    """
    Resolve /cd targets against the workspace, home directory, and cwd.
    `/cd Documents/Tes` should find ~/Documents/Tes, not <cwd>/Documents/Tes.
    """
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return None
    expanded = os.path.expanduser(raw)
    candidates = []
    if os.path.isabs(expanded):
        candidates.append(os.path.abspath(expanded))
    else:
        home = os.path.expanduser("~")
        if folder_aktif:
            candidates.append(os.path.abspath(os.path.join(folder_aktif, expanded)))
        candidates.append(os.path.abspath(os.path.join(home, expanded)))
        candidates.append(os.path.abspath(os.path.join(os.getcwd(), expanded)))
        # Common Windows shorthand: Documents\\Foo from anywhere
        docs = os.path.join(home, "Documents")
        candidates.append(os.path.abspath(os.path.join(docs, expanded)))
        if expanded.lower().startswith("documents"):
            rest = expanded[len("Documents"):].lstrip("\\/")
            candidates.append(os.path.abspath(os.path.join(docs, rest) if rest else docs))

    seen = set()
    for c in candidates:
        norm = os.path.normcase(os.path.normpath(c))
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isdir(c):
            return c
    return None


def suggest_cd_paths(raw: str, folder_aktif: str = None, limit: int = 5) -> list:
    """
    Nearby existing directories when resolve_cd_path misses.
    `/cd Documents/Tes` should surface Documents/TestingEditor if that folder exists.
    """
    import difflib
    raw = (raw or "").strip().strip('"').strip("'")
    if not raw:
        return []

    expanded = os.path.expanduser(raw)
    home = os.path.expanduser("~")
    docs = os.path.join(home, "Documents")
    parts = expanded.replace("\\", "/").rstrip("/").split("/")
    needle = (parts[-1] if parts else expanded).lower()
    if not needle:
        return []

    parents = []
    if os.path.isabs(expanded):
        parents.append(os.path.dirname(os.path.abspath(expanded)))
    else:
        rel_parent = os.path.dirname(expanded.replace("\\", "/"))
        if folder_aktif:
            parents.append(os.path.abspath(os.path.join(folder_aktif, rel_parent)) if rel_parent else folder_aktif)
        parents.append(os.path.abspath(os.path.join(home, rel_parent)) if rel_parent else home)
        parents.append(os.path.abspath(os.path.join(os.getcwd(), rel_parent)) if rel_parent else os.getcwd())
        parents.append(os.path.abspath(os.path.join(docs, rel_parent)) if rel_parent else docs)
        if expanded.lower().replace("\\", "/").startswith("documents/"):
            rest_parent = os.path.dirname(expanded.replace("\\", "/")[len("documents/"):])
            parents.append(os.path.abspath(os.path.join(docs, rest_parent)) if rest_parent else docs)

    scored = []
    seen = set()
    for parent in parents:
        if not parent or not os.path.isdir(parent):
            continue
        try:
            names = os.listdir(parent)
        except OSError:
            continue
        for name in names:
            path = os.path.join(parent, name)
            if not os.path.isdir(path):
                continue
            norm = os.path.normcase(os.path.normpath(path))
            if norm in seen:
                continue
            seen.add(norm)
            base = name.lower()
            if base.startswith(needle):
                score = 1.0 + (0.1 if len(base) == len(needle) else 0.0)
            elif len(needle) >= 4 and needle in base:
                score = 0.7
            elif len(needle) >= 4:
                score = difflib.SequenceMatcher(None, needle, base).ratio()
                if score < 0.62:
                    continue
            else:
                continue
            scored.append((score, path))

    scored.sort(key=lambda x: (-x[0], x[1].lower()))
    return [p for _, p in scored[:limit]]


_LAST_EXECUTE_INTERACTIVE = False


def take_post_interactive_guard() -> bool:
    """True once after a TTY /run so leftover stdin is not sent to the AI."""
    global _LAST_EXECUTE_INTERACTIVE
    flag = _LAST_EXECUTE_INTERACTIVE
    _LAST_EXECUTE_INTERACTIVE = False
    return flag


def looks_like_leftover_program_input(user_input: str) -> bool:
    """Short leftover stdin after an interactive program already exited.

    Held only together with take_post_interactive_guard() in the main loop.
    Slash commands and real shell lines are never treated as leftover.
    Short replies (digits, math expressions) are held so they are not sent to the AI.
    """
    text = (user_input or "").strip()
    if not text or text.startswith("/") or text.startswith("!"):
        return False
    if looks_like_direct_shell(text):
        return False
    if len(text) > 12:
        return False
    if text.isdigit():
        return True
    if re.fullmatch(r"[0-9+\-*/().\s]+", text) and any(c.isdigit() for c in text):
        return True
    return False


def _list_runnable_root_files(folder_path: str) -> list:
    found = []
    try:
        for name in os.listdir(folder_path):
            if name in _SKIP_SCAN_DIRS:
                continue
            full = os.path.join(folder_path, name)
            if os.path.isfile(full) and os.path.splitext(name)[1].lower() in _SCRIPT_INTERPRETERS:
                found.append(name)
    except OSError:
        pass
    preferred = {"main.py", "app.py", "index.js", "main.js"}
    found.sort(key=lambda n: (0 if n.lower() in preferred else 1, n.lower()))
    return found


def detect_project_runner(folder_path: str, active_file: str = None) -> dict:
    """
    Menganalisis folder proyek dan file yang sedang aktif untuk menentukan
    cara terbaik menjalankan (run) proyek.
    """
    if not folder_path or not os.path.exists(folder_path):
        return {
            "type": "none",
            "label": "Run File",
            "command": "",
            "can_run": False,
            "description": "Open a project folder first"
        }

    package_json_path = os.path.join(folder_path, "package.json")
    artisan_path = os.path.join(folder_path, "artisan")
    composer_json_path = os.path.join(folder_path, "composer.json")
    manage_py_path = os.path.join(folder_path, "manage.py")

    # 1. Deteksi Django (manage.py)
    if os.path.exists(manage_py_path):
        return {
            "type": "django",
            "label": "Serve Django",
            "command": f"{sys.executable} \"{manage_py_path}\" runserver",
            "can_run": True,
            "is_server": True,
            "description": "Menjalankan Django Server pada http://127.0.0.1:8000"
        }

    # 2. Deteksi React / Vite / Next.js / Node (package.json)
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                pkg_data = json.load(f)
            scripts = pkg_data.get("scripts", {})
            if "dev" in scripts:
                return {
                    "type": "node_dev",
                    "label": "Start Dev Server",
                    "command": "npm run dev",
                    "can_run": True,
                    "is_server": True,
                    "description": "Menjalankan Node/Vite/React dev server"
                }
            elif "start" in scripts:
                return {
                    "type": "node_start",
                    "label": "Start App (npm)",
                    "command": "npm start",
                    "can_run": True,
                    "is_server": True,
                    "description": "Menjalankan Node/React app"
                }
        except Exception:
            pass

    # 3. Deteksi Laravel / PHP
    if os.path.exists(artisan_path):
        return {
            "type": "laravel",
            "label": "Serve Laravel",
            "command": "php artisan serve",
            "can_run": True,
            "is_server": True,
            "description": "Menjalankan Laravel Server pada http://127.0.0.1:8000"
        }
    elif os.path.exists(composer_json_path):
        return {
            "type": "php",
            "label": "Run PHP Server",
            "command": "php -S localhost:8000",
            "can_run": True,
            "is_server": True,
            "description": "Menjalankan PHP Built-in Server"
        }

    # 4. Deteksi File Aktif di Editor
    if active_file:
        ext = os.path.splitext(active_file)[1].lower()
        file_abs = os.path.join(folder_path, active_file)
        file_name = os.path.basename(active_file)

        if ext in [".html", ".htm"]:
            return {
                "type": "html_preview",
                "label": "Live Preview",
                "command": "preview",
                "can_run": True,
                "is_server": False,
                "is_preview": True,
                "file": active_file,
                "description": f"Buka live preview untuk {active_file}"
            }
        elif ext == ".py":
            return {
                "type": "python",
                "label": f"Run Python ({file_name})",
                "command": f"{sys.executable} -u \"{file_abs}\"",
                "can_run": True,
                "is_server": False,
                "file": active_file,
                "description": f"Eksekusi script {active_file} dengan Python"
            }
        elif ext in [".js", ".ts", ".mjs"]:
            return {
                "type": "node_script",
                "label": f"Run Node ({file_name})",
                "command": f"node \"{file_abs}\"",
                "can_run": True,
                "is_server": False,
                "file": active_file,
                "description": f"Eksekusi {active_file} dengan Node.js"
            }

    # 5. Fallback Root Files
    main_py = os.path.join(folder_path, "main.py")
    app_py = os.path.join(folder_path, "app.py")
    index_html = os.path.join(folder_path, "index.html")

    if os.path.exists(main_py):
        return {
            "type": "python",
            "label": "Run Python (main.py)",
            "command": _quote_cmd([sys.executable, "-u", main_py]),
            "can_run": True,
            "is_server": False,
            "file": "main.py",
            "description": "Eksekusi main.py dengan Python"
        }
    elif os.path.exists(app_py):
        return {
            "type": "python",
            "label": "Run Python (app.py)",
            "command": _quote_cmd([sys.executable, "-u", app_py]),
            "can_run": True,
            "is_server": False,
            "file": "app.py",
            "description": "Eksekusi app.py dengan Python"
        }
    elif os.path.exists(index_html):
        return {
            "type": "html_preview",
            "label": "Live Preview",
            "command": "preview",
            "can_run": True,
            "is_server": False,
            "is_preview": True,
            "file": "index.html",
            "description": "Live preview index.html"
        }

    runnable = _list_runnable_root_files(folder_path)
    if runnable:
        chosen = runnable[0]
        wrapped = wrap_script_command(chosen, folder_path)
        ext = os.path.splitext(chosen)[1].lower()
        return {
            "type": "python" if ext == ".py" else "script",
            "label": f"Run {chosen}",
            "command": wrapped,
            "can_run": True,
            "is_server": False,
            "file": chosen,
            "description": f"Eksekusi {chosen}"
        }

    # One-level nested main.py / app.py (e.g. kalkulator/main.py)
    try:
        for name in os.listdir(folder_path):
            if name in _SKIP_SCAN_DIRS:
                continue
            sub = os.path.join(folder_path, name)
            if not os.path.isdir(sub):
                continue
            for candidate in ("main.py", "app.py"):
                nested = os.path.join(sub, candidate)
                if os.path.isfile(nested):
                    rel = os.path.join(name, candidate)
                    return {
                        "type": "python",
                        "label": f"Run Python ({rel})",
                        "command": wrap_script_command(rel, folder_path),
                        "can_run": True,
                        "is_server": False,
                        "file": rel,
                        "description": f"Eksekusi {rel}"
                    }
    except OSError:
        pass

    return {
        "type": "generic",
        "label": "Run File",
        "command": "",
        "can_run": False,
        "description": "Buka file kode (.py, .js, .html) untuk menjalankan"
    }


def execute_script(command: str, cwd: str, timeout: int = 30, interactive: bool = False) -> dict:
    """
    Run a command in cwd.

    interactive=True inherits stdin/stdout/stderr so input() and live output
    work in the Klyro CLI. Capture mode is used for short AI-issued commands.
    """
    global _LAST_EXECUTE_INTERACTIVE
    _LAST_EXECUTE_INTERACTIVE = bool(interactive)
    command = wrap_script_command(command, cwd)
    start_time = time.time()
    try:
        if interactive:
            print()  # blank line so program prompts sit on their own line
            proc = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                timeout=None,
                env=_get_execution_env(),
            )
            duration = round(time.time() - start_time, 2)
            return {
                "success": proc.returncode == 0,
                "stdout": "",
                "stderr": "",
                "exit_code": proc.returncode,
                "duration": f"{duration}s",
                "interactive": True,
            }

        proc = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=_get_execution_env()
        )
        duration = round(time.time() - start_time, 2)
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "duration": f"{duration}s"
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Execution exceeded the time limit ({timeout}s). For server processes, use background mode.",
            "exit_code": -1,
            "duration": f"{timeout}s"
        }
    except KeyboardInterrupt:
        duration = round(time.time() - start_time, 2)
        return {
            "success": False,
            "stdout": "",
            "stderr": "Interrupted by user.",
            "exit_code": 130,
            "duration": f"{duration}s",
            "interactive": interactive,
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": friendly("Could not execute the command", e),
            "exit_code": 1,
            "duration": "0s"
        }


def start_server_process(command: str, cwd: str) -> dict:
    """
    Menjalankan server background (npm run dev, php artisan serve, dsb).
    """
    global running_process, process_logs
    stop_server_process()

    process_logs = [
        f"[Klyro Runner] Starting server: {command}\n"
        f"[Folder]: {cwd}\n"
        + "="*50 + "\n"
    ]

    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=_get_execution_env()
        )
        running_process = proc

        def reader():
            try:
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        process_logs.append(line)
                        if len(process_logs) > 1000:
                            process_logs.pop(0)
            except Exception:
                pass

        t = threading.Thread(target=reader, daemon=True)
        t.start()

        return {
            "success": True,
            "message": f"Server started: {command}",
            "is_running": True
        }
    except Exception as e:
        return {"success": False, "error": friendly("Could not start the server", e), "is_running": False}


def stop_server_process() -> dict:
    """
    Menghentikan server background beserta seluruh child process di Windows/Linux.
    """
    global running_process, process_logs
    if running_process and running_process.poll() is None:
        try:
            pid = running_process.pid
            if sys.platform == "win32":
                # Kill seluruh process tree di Windows
                subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, capture_output=True)
            else:
                running_process.terminate()

            running_process = None
            process_logs.append("\n[Klyro Runner] 🛑 Server process stopped successfully.\n")
            return {"success": True, "message": "Process stopped successfully."}
        except Exception as e:
            return {"success": False, "error": friendly("Could not stop the process", e)}
    return {"success": True, "message": "No process is currently running."}


def get_runner_status() -> dict:
    """
    Mengecek status proses background & mengambil log terbaru.
    """
    global running_process, process_logs
    is_running = bool(running_process and running_process.poll() is None)
    return {
        "is_running": is_running,
        "logs": "".join(process_logs)
    }
