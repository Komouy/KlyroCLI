import os

# ─────────────────────────────────────────────
# GEMINI CONFIG
# ─────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Alias lama agar tidak break file lain
API_KEY = GEMINI_API_KEY

# Model Gemini — Auto-Selection
MODEL_KECIL = "gemini-3.5-flash-lite"   # Ringan, gratis, untuk proyek kecil
MODEL_BESAR = "gemini-3.6-flash"        # Lebih kuat, untuk proyek menengah/besar

# ─────────────────────────────────────────────
# GROQ CONFIG
# ─────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Model Groq default
GROQ_MODEL_CEPAT  = "groq/compound-mini"    # ⚡ Default — ringan & cepat
GROQ_MODEL_PINTAR = "openai/gpt-oss-120b"   # 🧠 Paling kuat — GPT open-source 120B

# Katalog semua model Groq yang tersedia (untuk dropdown UI)
GROQ_MODELS_CATALOG = [
    # ── Chat Models ────────────────────────────────────────────
    { "id": "openai/gpt-oss-120b",  "label": "GPT OSS 120B",     "tag": "🏆 Terkuat",  "group": "OpenAI OSS" },
    { "id": "openai/gpt-oss-20b",   "label": "GPT OSS 20B",      "tag": "⚡ Cepat",    "group": "OpenAI OSS" },
    { "id": "groq/compound",        "label": "Groq Compound",     "tag": "🔥 Flagship", "group": "Groq"       },
    { "id": "groq/compound-mini",   "label": "Groq Compound Mini","tag": "⚡ Ringan",   "group": "Groq"       },
    { "id": "qwen/qwen3.8-27b",     "label": "Qwen3 27B (v8)",   "tag": "🧠 Akurat",   "group": "Qwen"       },
    { "id": "qwen/qwen3.6-27b",     "label": "Qwen3 27B (v6)",   "tag": "🧠 Akurat",   "group": "Qwen"       },
    { "id": "allam-2-7b",           "label": "Allam 2 7B",       "tag": "🌍 Arabic",   "group": "Other"      },
    # ── Audio Models (tidak untuk chat) ────────────────────────
    # { "id": "whisper-large-v3",      "label": "Whisper v3",     "tag": "🎤 Audio" },
]

# Batas konteks Groq — dinaikkan dari 8_000. Nilai lama itu jauh lebih kecil
# dari ukuran satu file source code menengah saja (mis. ai.py ~32rb karakter),
# jadi AI sering "menulis buta" tanpa pernah benar-benar melihat isi file
# yang diminta untuk diedit. Model default Groq sekarang (gpt-oss-120b)
# mendukung context window besar, jadi disamakan dengan tier Cerebras.
GROQ_MAX_KONTEKS_CHARS = 32_000

# Provider default (bisa: "gemini" atau "groq")
DEFAULT_PROVIDER = "gemini"

# ─────────────────────────────────────────────
# ROUTING THRESHOLD
# ─────────────────────────────────────────────
# Jika total karakter > 25.000 atau file > 5 -> Gemini Besar
# Di bawah itu -> Gemini Lite / Groq
AMBANG_BATAS_KARAKTER    = 25_000
AMBANG_BATAS_JUMLAH_FILE = 5

# ─────────────────────────────────────────────
# BATASAN UKURAN & KONTEKS
# ─────────────────────────────────────────────
MAKS_UKURAN_FILE    = 100 * 1024    # 100 KB per file
MAKS_TOTAL_KONTEKS  = 500_000       # 500.000 karakter total

# ─────────────────────────────────────────────
# WHITELIST & IGNORE
# ─────────────────────────────────────────────
EKSTENSI_DIIZINKAN = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".txt", ".json", ".html", ".css", ".md",
    ".yaml", ".yml", ".sql", ".sh", ".bat", ".c", ".cpp", ".java"
}

FOLDER_DIABAIKAN = {
    ".git", ".github", "__pycache__", "node_modules",
    ".venv", "venv", "env", ".idea", ".vscode", "dist", "build",
    "AppData", "Application Data", ".gemini", ".cache", ".npm", ".cargo",
    "Music", "Videos", "Pictures", "Searches", "Contacts", "Saved Games",
    "Links", "Favorites", ".matplotlib", ".dotnet", ".nuget"
}
