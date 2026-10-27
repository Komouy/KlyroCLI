<div align="center">

# ❄️ Klyro Code (KlyroCLI)
**Autonomous, Multi-Provider Agentic AI Coding Assistant in Your Terminal**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-38bdf8.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-34d399.svg?style=flat-square)](LICENSE)
[![Theme: Nordic Frost](https://img.shields.io/badge/Theme-Nordic%20Frost-bae6fd.svg?style=flat-square)](https://github.com/Komouy/KlyroCLI)
[![Tests: 223 Passed](https://img.shields.io/badge/Tests-223%20Passed-818cf8.svg?style=flat-square)](https://github.com/Komouy/KlyroCLI)
[![Architecture: Zero Dependency Core](https://img.shields.io/badge/Core-Zero%20Dep%20SSE-38bdf8.svg?style=flat-square)](https://github.com/Komouy/KlyroCLI)

*Terinspirasi dari Claude Code, dirancang untuk kecepatan inferensi ultra-tinggi (~500 tok/s), kebebasan multi-provider tanpa batas, dan kendali penuh pengembang.*

[Fitur Unggulan](#-fitur-unggulan) •
[Instalasi](#-instalasi-cepat) •
[Setup Provider Gratis](#-setup-provider-gratis-tanpa-kartu-kredit) •
[Panduan Coding](#-panduan-praktis-untuk-coding-sehari-hari) •
[Panduan Belajar](#-panduan-praktis-untuk-belajar--study) •
[Daftar Perintah](#-referensi-slash-commands)

</div>

---

## ⚡ Mengapa KlyroCLI Sangat Cocok untuk Coding & Belajar?

KlyroCLI bukan sekadar wrapper API biasa. Klyro adalah **pair-programmer AI terminal-native** yang memahami seluruh workspace Anda, memiliki sistem **penyelarasan model resmi dari dokumentasi web**, dan dibentengi guardrails keamanan.

### 💡 Keunggulan untuk Coding Sehari-hari:
* **Multi-Provider Freedom**: Terhubung mulus ke **Google Gemini**, **Groq LPU**, **DeepSeek**, **OpenRouter**, **Anthropic Claude**, **OpenAI**, dan **Ollama Lokal**.
* **Universal Auto-Recovery**: Jika kuota gratis satu provider habis (429/ResourceExhausted), Smart Router secara otomatis memindahkan sesi ke provider cadangan tanpa menghentikan pekerjaan Anda.
* **Unified Visual Diff & Syntax Safety**: Setiap perubahan file menampilkan preview diff yang jelas dan otomatis divalidasi sintaksnya (misal `ast.parse` Python) sebelum disimpan.
* **Instant Rollback (`/undo`)**: Salah edit? Cukup ketik `/undo` untuk mengembalikan file ke kondisi sebelum diubah AI.
* **Automated Conventional Git Commit (`/commit`)**: Membaca staged/unstaged git diff dan otomatis membuat commit message standar industri (`feat:`, `fix:`, `refactor:`).
* **Terminal Safety Interceptor**: Menjaga sistem dari perintah mematikan seperti `rm -rf /`, `del`, atau formatting disk.

### 🎓 Keunggulan untuk Belajar (Learning & Study):
* **Consensus Engine (`/consensus`)**: Tanyakan algoritma atau masalah rumit, lalu tonton 2–3 model AI berbeda (Gemini vs Groq Llama 70B vs DeepSeek R1) berdiskusi secara paralel, di mana **AI Judge** akan menyintesis jawaban terbaik dan menyorot potensi *edge-case*.
* **Official Model Docs Sync (`/sync-models`)**: Sistem cerdas yang dapat membaca dokumentasi resmi penyedia AI di website mereka untuk memperbarui katalog model resmi terkini secara mandiri.
* **100% Gratis & Hemat Biaya**: Anda bisa menggunakan Google Gemini Flash (1M context) dan Groq LPU (~500 tok/s) secara cuma-cuma tanpa kartu kredit.
* **Built-in Docs (`/docs`)**: Baca panduan dan tips programming langsung di terminal tanpa membuka browser.

---

## 🚀 Instalasi Cepat

### Prasyarat
- **Python 3.10** atau lebih tinggi
- **Git** (opsional, untuk integrasi `/commit` dan `/diff`)

---

### 1. Windows (CMD / PowerShell)
```powershell
# Clone repositori
git clone https://github.com/Komouy/KlyroCLI.git
cd KlyroCLI

# Buat virtual environment & install dependensi
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```
> **Tip Windows**: Anda juga bisa langsung menjalankan `klyro.bat` atau `KlyroCLI.bat` dengan sekali klik!

---

### 2. macOS & Linux
```bash
git clone https://github.com/Komouy/KlyroCLI.git
cd KlyroCLI

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

---

### 3. Android Mobile (Termux)
KlyroCLI sangat ringan dan berjalan lancar di smartphone Android:
```bash
pkg update && pkg install python git -y
git clone https://github.com/Komouy/KlyroCLI.git
cd KlyroCLI
pip install -r requirements.txt
python klyro_cli.py
```

---

## 🔑 Setup Provider Gratis Tanpa Kartu Kredit

KlyroCLI langsung bisa digunakan tanpa biaya sepeser pun. Jalankan Klyro, lalu ketik `/provider`:

```text
/provider
```

Pilih provider yang Anda inginkan:

### 1. Google Gemini (Paling Direkomendasikan untuk Pemula)
* **Kelebihan**: Gratis, batas konteks 1 Juta token (bisa membaca seluruh file proyek sekaligus), multimodal.
* **Cara Dapatkan Key**: Buka [aistudio.google.com](https://aistudio.google.com), login dengan akun Google, klik **"Get API key"**, lalu salin kuncinya ke Klyro.

### 2. Groq LPU (Paling Cepat di Dunia ~500 tok/s)
* **Kelebihan**: Inferensi secepat kilat menggunakan chip LPU, model Llama 3.3 70B & DeepSeek R1 gratis.
* **Cara Dapatkan Key**: Buka [console.groq.com](https://console.groq.com), buat akun gratis, buat API key baru.

### 3. OpenRouter (Model Open-Source Gratis)
* **Kelebihan**: Akses ke model GLM, MiniMax, Qwen, dan puluhan model komunitas secara gratis.
* **Cara Dapatkan Key**: Buka [openrouter.ai](https://openrouter.ai), buat akun, dan buat API key.

### 4. Ollama (100% Offline Tanpa Internet)
* Jalankan Ollama di komputer Anda (`ollama run qwen2.5-coder:7b`).
* Di Klyro, pilih provider **Custom / Ollama**, endpoint default otomatis terhubung ke `http://localhost:11434/v1`.

---

## 💻 Panduan Praktis untuk Coding Sehari-hari

### Alur Kerja 1: Eksplorasi Proyek Baru
```text
# 1. Buka Klyro di folder proyek Anda:
klyro

# 2. Lihat struktur folder dan file proyek:
/tree
/files

# 3. Cari fungsi atau kelas spesifik di seluruh file:
/symbols def calculate_tax
/find **/*.ts
```

### Alur Kerja 2: Menanyakan & Mengedit Kode dengan Context Mention (`@`)
Sebutkan nama file menggunakan simbol `@` untuk memasukkan isinya ke dalam konteks AI:
```text
Tolong refactor fungsi authenticateUser di @auth.py agar mendukung JWT refresh token
```
Klyro akan membaca `@auth.py`, menyusun perbaikan, dan menampilkan **unified diff**. Anda akan diminta konfirmasi persetujuan (*approval gate*) sebelum file benar-benar diubah.

### Alur Kerja 3: Menjalankan Perintah Terminal
Gunakan tanda seru `!` untuk menjalankan perintah terminal tanpa keluar dari Klyro:
```text
!npm test
!pytest tests/
!git status
```
Atau gunakan auto-runner Klyro:
```text
/run
```

### Alur Kerja 4: Simpan Perubahan ke Git & Rollback
```text
# Lihat perubahan lokal uncommitted:
/diff

# Buat conventional commit message otomatis dan commit ke git:
/commit

# Jika hasil kode AI kurang memuaskan, kembalikan file ke kondisi semula:
/undo
```

---

## 🎓 Panduan Praktis untuk Belajar & Study

### 1. Membedah Masalah dengan Consensus Engine (`/consensus`)
Aktifkan mode konsensus:
```text
/consensus
```
Lalu tanyakan konsep yang sulit atau soal algoritma:
```text
Jelaskan perbedaan threading vs asyncio di Python beserta contoh race condition-nya
```
**Apa yang terjadi?**
Klyro akan mengeksekusi Google Gemini, Groq Llama-3.3 70B, dan DeepSeek R1 secara bersamaan. Kemudian **AI Judge** akan mengevaluasi jawaban ketiganya, membandingkan logika masing-masing model, dan merangkum penjelasan paling komprehensif untuk Anda.

### 2. Menyelaraskan Model Resmi Terkini (`/sync-models`)
Provider AI sering merilis model baru dan memensiunkan model lama. Agar Klyro selalu mutakhir:
```text
/sync-models
```
Klyro akan membaca website dokumentasi resmi (`ai.google.dev`, `console.groq.com`, `api-docs.deepseek.com`, dll), menyaring model yang benar-benar aktif, dan memperbarui menu `/cmodel` Anda secara otomatis.

### 3. Membaca Panduan & Tips Langsung di Terminal (`/docs`)
```text
/docs quickstart     # Panduan memulai cepat
/docs commands       # Daftar perintah slash lengkap
/docs providers      # Konfigurasi AI provider
/docs tips           # Trik efisiensi token & konteks
```

---

## 📖 Referensi Slash Commands

| Perintah | Deskripsi Singkat |
| :--- | :--- |
| `/help` | Menampilkan palet perintah lengkap |
| `/provider` (atau `/p`) | Mengatur provider AI aktif dan mengelola API key |
| `/cmodel` (atau `/m`) | Melihat daftar model aktif dan berpindah model |
| `/sync-models` (atau `/sync`) | Sinkronisasi model resmi langsung dari website dokumentasi provider |
| `/consensus` | Mengaktifkan/menonaktifkan mode diskusi multi-AI paralel + AI Judge |
| `/router [auto\|off]` | Mode otomatis pemilihan model berdasarkan beban kerja (*workload tier*) |
| `/think [auto\|on\|off]` | Menampilkan proses berpikir mendalam AI (*Chain of Thought*) |
| `/doctor` (atau `/doc`) | Diagnostik kesehatan sistem, encoding UTF-8, network ping, dan API key |
| `/docs [topik]` | Membaca dokumentasi internal Klyro langsung di terminal |
| `/commit` | Menganalisis diff dan mengeksekusi git commit otomatis |
| `/diff` | Memeriksa perubahan kode lokal yang belum di-commit |
| `/undo` (atau `/u`) | Membatalkan modifikasi file terakhir yang dilakukan oleh AI |
| `/files` | Menampilkan seluruh file proyek beserta ukurannya |
| `/tree` | Menampilkan visualisasi pohon direktori (*folder tree*) |
| `/find [glob]` | Mencari file dengan pola glob (misal: `**/*.py`, `src/**/*.tsx`) |
| `/symbols <query>` | Mencari fungsi, class, atau variabel di seluruh codebase |
| `/run [cmd]` | Menjalankan script proyek atau test runner secara otomatis |
| `/todo` | Memindai komentar `TODO`, `FIXME`, dan `HACK` di seluruh workspace |
| `/usage` (atau `/stat`) | Memeriksa konsumsi token, kecepatan inferensi (tok/s), dan estimasi biaya |
| `/history` | Menampilkan atau membersihkan riwayat percakapan sesi |
| `/clear` (atau `/cls`) | Membersihkan layar terminal |
| `!command` | Menjalankan perintah shell langsung (misal: `!cargo build`, `!npm start`) |
| `/exit` (atau `/q`) | Keluar dari KlyroCLI |

---

## 🩺 Diagnostik & Pemecahan Masalah (`/doctor`)

Jika Anda mengalami kendala koneksi atau API key:
```text
/doctor
```
Sistem akan memeriksa:
* ✔ **Python Runtime**: Mendukung Python 3.10 hingga 3.14+
* ✔ **Console Encoding**: UTF-8 auto-configuration di Windows/Linux
* ✔ **Workspace Permissions**: Akses baca & tulis file
* ✔ **Git Integration**: Ketersediaan tool git lokal
* ✔ **Internet Latency**: Mengukur kecepatan ping ke gateway
* ✔ **AI Gateways**: Memvalidasi status keaktifan masing-masing API key
* ✔ **Security Interceptor**: Memastikan sandbox path aktif

---

## 🛡️ Keamanan & Privasi

* **Kunci API Anda Aman**: Semua kunci disimpan secara lokal di file `klyro_config.json` di mesin Anda dan otomatis diabaikan oleh `.gitignore`. Tidak ada kunci yang pernah dikirim ke server Klyro.
* **Sandbox Directory**: AI dibatasi hanya dapat membaca dan menulis di dalam folder proyek yang sedang aktif.
* **Dangerous Command Interceptor**: Perintah berbahaya seperti penghapusan partisi atau rekursif root dicegat sebelum dijalankan.

---

## 📄 Lisensi

Didistribusikan di bawah lisensi terbuka [MIT License](LICENSE).
Dikembangkan untuk komunitas pengembang dan pelajar oleh [Komouy](https://github.com/Komouy).
