# ❄️ Klyro Code (KlyroCLI) — User & Developer Guide

> **Autonomous, Multi-Provider Agentic AI Coding Assistant in Your Terminal.**  
> *Inspired by Claude Code, built for speed, multi-provider flexibility, and total developer control.*

---

## 📑 Table of Contents
1. [Overview & Key Features](#-overview--key-features)
2. [Quick Installation](#-quick-installation)
3. [Starting Klyro](#-starting-klyro)
4. [Slash Commands Reference](#-slash-commands-reference)
5. [Multi-Provider & Model Setup](#-multi-provider--model-setup)
6. [Smart Routing & Auto-Fallback](#-smart-routing--auto-fallback)
7. [Session Memory & Token Usage Tracker](#-session-memory--token-usage-tracker)
8. [System Health Diagnostics (`/doctor`)](#-system-health-diagnostics-doctor)
9. [Safety & Security Guardrails](#-safety--security-guardrails)
10. [Architecture & Project Structure](#-architecture--project-structure)
11. [Troubleshooting & FAQ](#-troubleshooting--faq)

---

## 🌟 Overview & Key Features

KlyroCLI is a terminal-native AI pair programmer that can read your entire workspace, edit files with unified visual diffs, execute shell commands, manage directories, and switch seamlessly across **8 major AI providers**.

- 🎨 **Nordic Frost Aesthetics**: Clean, modern ANSI color palette with live spinners and real-time streaming.
- ⚡ **Multi-Provider Engine**: Google Gemini, Groq LPU, Cerebras, OpenRouter (Free), Mistral AI, DeepSeek, OpenAI, and Local Ollama.
- ⌨️ **Interactive Slash Autocomplete**: Type `/` to see instant command suggestions, keyboard navigation, and inline descriptions.
- 📎 **Smart File Mention (`@filename`)**: Pin exact file contents directly into AI context with `@` autocomplete just like Claude Code & Cursor.
- 🔄 **Universal Auto-Fallback**: Never get blocked if an API quota runs out — Klyro automatically failovers to the next available provider.
- 🛡️ **Safety Guardrails**: Sandbox directory protection (`is_safe_path`) and dangerous command interception (`rm -rf /`, formatting, recursive deletions).
- 📊 **Usage & Cost Tracking (`/usage`)**: Transparent token consumption, latency, and estimated cost tracking.
- 📁 **Per-Project Session History (`/history`)**: Locally persists past prompts and code decisions in `.klyro/history.json`.
- 🩺 **System Diagnostics (`/doctor`)**: One-command health check for runtime, API keys, network ping, and write permissions.

---

## 🚀 Quick Installation

### Prerequisites
- Python **3.10** or higher
- Git (optional, for `/diff` and git integrations)

### 1. Clone & Setup
```bash
git clone https://github.com/your-username/KlyroCLI.git
cd KlyroCLI
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
# or install as an editable global CLI:
pip install -e .
```

---

## ⚡ Starting Klyro

Once installed, you can start Klyro from **any directory or terminal**:

```bash
KlyroCLI
```
*or shorthand:*
```bash
klyro
```

You will see the Nordic Frost startup banner:
```
  ✓ klyro code · ready
  ┌  klyro code · v2.5.0
  │  workspace : my-project (14 files)
  │  engine    : GROQ LPU • openai/gpt-oss-120b
  └  ready     : Type anything to code, or /help for commands
```

---

## 🛠️ Slash Commands Reference

| Command | Shorthand | Description |
| :--- | :--- | :--- |
| `/help` | `/?`, `/h` | Displays the interactive help menu with all commands |
| `/doctor` | `/doc` | Runs comprehensive system, API, network, and security diagnostics |
| `/provider` | `/setup`, `/p` | Opens interactive wizard to switch AI providers & set API keys |
| `/cmodel [name\|num]` | `/model`, `/m` | Lists models with recommendations or switches active model |
| `/usage` | `/stat`, `/stats` | Displays session uptime, total tokens, latency, speed (tok/s), and costs |
| `/history [clear]` | — | Views recent interaction history or clears `.klyro/history.json` |
| `/files` | — | Lists all scanned workspace files with their file sizes in KB |
| `/tree` | — | Generates a clean visual directory tree of the workspace |
| `/run [cmd]` | — | Auto-detects and runs project scripts (npm, python, cargo, etc.) |
| `/commit` | — | Automatically generates conventional commit message & commits changes |
| `/undo` | `/u` | Reverts the last AI-made file modifications (create/edit/delete) |
| `/registry [refresh]` | — | Shows the OpenRouter model registry, or refreshes it from the API |
| `/todo` | — | Scans the workspace for `TODO` / `FIXME` comments |
| `/consensus` | — | Toggles multi-model consensus mode (parallel query + AI judge across all configured providers for coding questions) |
| `/diff` | — | Displays uncommitted Git changes in the workspace |
| `/clear` | `/cls` | Clears the terminal screen and resets visual display |
| `/cd <path>` | — | Changes the active project directory on the fly |
| `/exit` | `/quit`, `/q` | Exits the Klyro CLI session |
| `!command` | — | Executes a shell command directly (e.g. `!git status`, `!npm test`) |

---

## 🤖 Multi-Provider & Model Setup

To configure or change your AI engine, type:
```
/provider
```

### Supported Providers & Free Tiers:

1. **Google Gemini** *(Recommended Default)*:
   - **Key Source:** [aistudio.google.com](https://aistudio.google.com) *(Free tier available)*
   - **Models:** `gemini-3.6-flash` (Recommended), `gemini-3.5-flash-lite`, `gemini-3.1-pro-preview`
2. **Groq LPU** *(Ultra Fast ~500 tok/s)*:
   - **Key Source:** [console.groq.com](https://console.groq.com) *(Free tier available)*
   - **Models:** `openai/gpt-oss-120b` (Flagship 120B), `groq/compound-mini`, `qwen/qwen3.8-27b`
3. **OpenRouter** *(300+ Free Models)*:
   - **Key Source:** [openrouter.ai](https://openrouter.ai) *(No CC required)*
   - **Models:** `meta-llama/llama-3.3-70b-instruct:free`, `google/gemma-3-27b-it:free`, `openrouter/free`
4. **Mistral AI** *(Experiment Tier)*:
   - **Key Source:** [console.mistral.ai](https://console.mistral.ai)
   - **Models:** `mistral-small-latest`, `codestral-latest` (Coding Specialist)
5. **Cerebras**:
   - **Key Source:** [cloud.cerebras.ai](https://cloud.cerebras.ai)
   - **Models:** `gpt-oss-120b`, `gemma-4-31b`, `llama-3.3-70b`
6. **DeepSeek**:
   - **Key Source:** [platform.deepseek.com](https://platform.deepseek.com)
   - **Models:** `deepseek-chat` (V3), `deepseek-reasoner` (R1 Thinking Mode)
7. **OpenAI**:
   - **Key Source:** [platform.openai.com](https://platform.openai.com)
   - **Models:** `gpt-4o-mini`, `gpt-4o`, `o3-mini`
8. **Custom / Local Ollama**:
   - **Endpoint:** `http://localhost:11434/v1` *(No API key required)*
   - **Models:** `llama3`, `qwen2.5-coder`, `deepseek-r1`, `mistral`

---

## 🧠 Smart Routing & Auto-Fallback

### Dynamic Task Routing
Klyro automatically balances performance and quota:
- **Lightweight Tasks** *(chat, simple questions, small scripts)*: Uses fast, economical models (`gemini-3.5-flash-lite`, `groq/compound-mini`).
- **Heavy Tasks** *(full-repo refactors, architectural analysis)*: Routes to large-context models (`gemini-3.6-flash`, `gpt-oss-120b`).

### Universal Auto-Fallback
If your active provider hits a daily rate limit or exhausted quota (`429 Too Many Requests` or `402 Payment Required`), Klyro automatically shifts the request to your backup provider and continues streaming without dropping your turn.

---

## 📊 Session Memory & Token Usage Tracker

### 1. `/usage` — Real-Time Metrics Dashboard
Track performance, token throughput, and expenses:
```
  Session Usage & Metrics
  ┌──────────────────────────────────────────────────────┐
  │  Session Uptime : 18m 42s
  │  Total Queries  : 9 requests
  │  Total Tokens   : ~5,280 tok (Prompt: 3,400 │ Resp: 1,880)
  │  Avg Speed      : 210.4 tok/s (Avg Latency: 1.15s)
  │  Estimated Cost : $0.0000 (Free Tier / No Cost)
  │
  │  Engines Active in Session:
  │    • GROQ       : 6 queries (~3,500 tokens)
  │    • GEMINI     : 3 queries (~1,780 tokens)
  └──────────────────────────────────────────────────────┘
```

### 2. `/history` — Local Session History
All interactions are recorded in your workspace under `.klyro/history.json` so you can inspect past prompts and code updates across sessions.
- View history: `/history`
- Clear project history: `/history clear`

---

## 🩺 System Health Diagnostics (`/doctor`)

Run `/doctor` to perform an instant self-check on your environment:
- ✅ Python version compatibility
- ✅ Console UTF-8 capabilities
- ✅ Workspace read/write permissions
- ✅ Git installation & repository detection
- ✅ Internet connection & DNS latency
- ✅ Live ping test to configured AI providers
- ✅ Security guardrail verification

---

## 🛡️ Safety & Security Guardrails

Klyro includes built-in protective measures to keep your machine safe:

1. **Path Traversal Protection (`is_safe_path`)**:
   - Ensures AI file operations (`DELETE`, `RENAME`, `MKDIR`, write) never escape the root project directory.
2. **Dangerous Command Interceptor**:
   - Intercepts destructive patterns (e.g. `rm -rf /`, `del /s /q C:\`, disk formatting) and prompts for explicit human confirmation.
3. **Binary & Large File Filter**:
   - Automatically skips compiled binaries (`.exe`, `.dll`), archives (`.zip`), and large media files from being ingested into token context.
4. **Git Safety (`.gitignore`)**:
   - Automatically prevents `klyro_config.json`, `.env`, and session logs from being committed to public version control.

---

## 📁 Architecture & Project Structure

```
KlyroCLI/
├── klyro_cli.py         # Main CLI entry point, prompt loop & UI renderer
├── ai.py                # AI core facade, multi-provider streaming & fallback
├── provider_manager.py  # Catalog, credentials store & model registry
├── openrouter_registry.py # Dynamic OpenRouter model registry & smart routing
├── session_manager.py   # Session history (.klyro/) & token usage metrics
├── doctor.py            # Self-diagnostic system health checker
├── security.py          # Dangerous command interceptor & sandbox guard
├── file_manager.py      # Safe file walker, parser, AST syntax validator & diff
├── runner.py            # Project script detection & sub-process runner
├── undo_manager.py      # Reverts AI file modifications (/undo)
├── config.py            # Global constants, thresholds & default model IDs
├── errors.py            # Shared helper for calm, user-facing error messages
├── theme.py             # Nordic Frost ANSI theme constants & styling
├── pyproject.toml       # Modern PEP 517 build & global CLI installation
├── .gitignore           # Git exclusion rules for secrets & cache
└── README.md            # Quickstart & project overview
```

---

## ❓ Troubleshooting & FAQ

#### Q: How do I run Klyro globally from any folder?
**A:** Run `pip install -e .` once from the `KlyroCLI` directory. Afterwards, simply open a new terminal window and type `KlyroCLI` or `klyro`.

#### Q: Why did I get a `404 Model Not Found` error?
**A:** Model names evolve frequently. Type `/cmodel` to view the latest verified model list for your active provider, or switch providers with `/provider`.

#### Q: How do I use local offline models with Ollama?
**A:** Start your Ollama server (`ollama serve`), then type `/provider` in Klyro, select `[8] Custom`, and set the Base URL to `http://localhost:11434/v1`.

#### Q: Where are my API keys stored?
**A:** Locally on your machine in `klyro_config.json`. This file is strictly excluded by `.gitignore` so your keys will never leak to GitHub.

---

*Made with ❄️ Nordic Frost Aesthetics for productive, autonomous AI coding.*
