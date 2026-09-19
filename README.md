<div align="center">

# ❄️ Klyro Code (KlyroCLI)
**Autonomous, Multi-Provider Agentic AI Coding Assistant in Your Terminal**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-38bdf8.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-34d399.svg?style=flat-square)](LICENSE)
[![Theme: Nordic Frost](https://img.shields.io/badge/Theme-Nordic%20Frost-bae6fd.svg?style=flat-square)](https://github.com)
[![Zero Dependency Core](https://img.shields.io/badge/Core-Zero%20Dep%20SSE-818cf8.svg?style=flat-square)](https://github.com)

*Inspired by Claude Code, built for blazing speed, multi-provider freedom, and complete developer control.*

</div>

---

## ⚡ Highlights

- **Multi-Provider Engine**: Switch seamlessly across **Google Gemini**, **Groq LPU**, **OpenRouter**, **Mistral AI**, **Cerebras**, **DeepSeek**, **OpenAI**, and **Local Ollama**.
- **Interactive Slash Autocomplete**: Type `/` to see live dropdown suggestions with inline command descriptions.
- **Smart Routing & Universal Auto-Fallback**: Automatically routes heavy tasks to flagship models and failovers if quota runs out.
- **Safety First**: Dangerous command interceptor (`del`, `rm -rf`, disk formatting) and sandbox path protection (`is_safe_path`).
- **Real-Time Token & Cost Dashboard (`/usage`)**: Transparent token throughput, latency (ms), speed (tok/s), and cost tracking.
- **Local Session Memory (`/history`)**: Retains project conversation context in `.klyro/history.json`.
- **System Doctor (`/doctor`)**: One-command diagnostic health check for environment, API keys, network ping, and write permissions.

---

## 🚀 Quickstart

### 1. Installation

**PC / Mac / Linux:**
```bash
git clone https://github.com/your-username/KlyroCLI.git
cd KlyroCLI
pip install -e .
```

**Mobile (Android via Termux):**
```bash
pkg update && pkg install python git -y
git clone https://github.com/your-username/KlyroCLI.git
cd KlyroCLI
pip install -r requirements.txt
python klyro_cli.py
```

### 2. Launch
```bash
KlyroCLI
# or shorthand:
klyro
# on mobile/Termux (if not installed via pip -e):
python klyro_cli.py
```

### 3. Setup Your AI Provider
Type `/provider` inside Klyro to choose your provider and enter your API Key:
```
  AI Provider Setup
  ┌────────────────────────────────────────────────────────┐
  │  1. Google Gemini             ● configured (Free Tier) │
  │  2. Groq LPU                  ● configured (500 tok/s) │
  │  3. OpenRouter                ○ Free Models Available  │
  │  4. Mistral AI                ○ Experiment Tier        │
  │  5. DeepSeek / OpenAI / Local ○ Custom Options         │
  └────────────────────────────────────────────────────────┘
```

---

## 📖 Commands at a Glance

| Command | Action |
| :--- | :--- |
| `/help` | View all available slash commands |
| `/doctor` | Run comprehensive system and API connectivity diagnostics |
| `/commit` | Auto-generate conventional commit message & execute git commit |
| `/provider` | Switch AI provider and manage API keys |
| `/cmodel` | View model list with recommendations or switch active model |
| `/usage` | View token usage, speed (tok/s), latency, and estimated cost |
| `/history` | View or clear per-project session history |
| `/files` | List scanned workspace files and sizes |
| `/tree` | Display interactive visual folder tree |
| `/run [cmd]` | Automatically detect and execute project runners |
| `/undo` | Revert last AI-made file modifications |
| `/registry [refresh]` | View or refresh the OpenRouter model registry |
| `/todo` | Scan the workspace for TODO & FIXME comments |
| `/consensus` | Toggle multi-model consensus mode (parallel query + AI judge) |
| `/diff` | Inspect Git uncommitted modifications |
| `/clear` | Clear terminal and replay startup header |
| `!command` | Execute shell command directly with safety interception |

---

## 📚 Full Documentation

Explore our dedicated documentation in [`docs/`](./docs/):
- 📖 [User Guide & Provider Setup](./docs/USER_GUIDE.md) — Complete usage, slash commands, and multi-provider configuration
- 🗺️ [Project Roadmap](./docs/ROADMAP.md) — Future milestones and architectural goals
- ⚡ [Core Agent Quickstart](./docs/COREAGENT_QUICKSTART.md) — Guide for autonomous core tools & extensions
- 🐞 [Debugging & Diagnostics](./docs/Debugging.md) — Troubleshooting common issues

---

## 📄 License

Distributed under the [MIT License](LICENSE).
