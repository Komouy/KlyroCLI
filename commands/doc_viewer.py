"""
commands/doc_viewer.py — Interactive Built-in Documentation & User Guide for KlyroCLI.

Accessible via the `/docs` slash command:
  /docs                 → interactive arrow-key topic menu
  /docs <topic>         → render one topic directly
  /docs help            → list every available topic
Note: `/doc` (singular) stays the shorthand for `/doctor` diagnostics.
"""

from __future__ import annotations

import sys
from typing import Callable

from cli.spinner import static_box_width
from cli.interactive_menu import interactive_select
from theme import (
    RESET, BOLD,
    FROST_CYAN, FROST_AQUA, FROST_ICE, FROST_MINT, FROST_INDIGO,
    FROST_CORAL, FROST_AMBER, FROST_WHITE, FROST_GRAY, FROST_DARK, FROST_GHOST,
    gradient_text,
)


def _render_box_header(title: str, width: int = 70) -> None:
    bw = static_box_width(width)
    print(f"\n  {FROST_CYAN}{BOLD}❄️  Klyro Documentation — {title}{RESET}")
    print(f"  {FROST_DARK}╭{'─'*bw}╮{RESET}")


def _render_box_footer(width: int = 70) -> None:
    bw = static_box_width(width)
    print(f"  {FROST_DARK}╰{'─'*bw}╯{RESET}\n")


def show_quickstart_guide() -> None:
    """Section 1: Quickstart & Basic Workflow."""
    _render_box_header("Panduan Cepat & Alur Kerja (Quickstart)", 72)
    BAR = f"  {FROST_DARK}│{RESET}"

    print(f"{BAR}  {FROST_MINT}{BOLD}1. Chatting & Perintah Coding Langsung{RESET}")
    print(f"{BAR}     Cukup ketik permintaanmu dalam bahasa alami di terminal Klyro:")
    print(f"{BAR}     {FROST_WHITE}❯ Buatkan REST API dengan FastAPI untuk Todo app{RESET}")
    print(f"{BAR}     {FROST_WHITE}❯ Refactor auth.py agar menggunakan async/await{RESET}")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_MINT}{BOLD}2. Menyematkan File Konteks (@filename){RESET}")
    print(f"{BAR}     Gunakan tanda {FROST_CYAN}@{RESET} untuk menyertakan file spesifik ke prompt LLM:")
    print(f"{BAR}     {FROST_WHITE}❯ Jelaskan fungsi calculate_tax di @services/billing.py{RESET}")
    print(f"{BAR}     {FROST_GRAY}(Tersedia autocomplete otomatis saat kamu mengetik @...){RESET}")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_MINT}{BOLD}3. Visual Diff & Persetujuan Perubahan File{RESET}")
    print(f"{BAR}     Saat AI mengusulkan perubahan file, Klyro menampilkan kartu diff:")
    print(f"{BAR}     {FROST_MINT}+ Baris baru{RESET}  {FROST_CORAL}- Baris dihapus{RESET}")
    print(f"{BAR}     Kamu memegang kendali penuh: ketik [y] untuk terima atau [n] tolak.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_MINT}{BOLD}4. Menjalankan Perintah Shell Langsung (!command){RESET}")
    print(f"{BAR}     Awali dengan tanda seru {FROST_CYAN}!{RESET} untuk menjalankan perintah OS:")
    print(f"{BAR}     {FROST_WHITE}❯ !git status{RESET}   atau   {FROST_WHITE}❯ !pytest tests/{RESET}")
    print(f"{BAR}     Dilengkapi pelindung keamanan terhadap perintah berbahaya (del, rm -rf).")
    _render_box_footer(72)


def show_commands_guide() -> None:
    """Section 2: Comprehensive Slash Commands Reference."""
    _render_box_header("Daftar Lengkap Perintah (/slash commands)", 74)
    BAR = f"  {FROST_DARK}│{RESET}"

    # Group 1: AI & Neural Engine
    print(f"{BAR}  {FROST_INDIGO}{BOLD}⌁ AI & Model Control{RESET}")
    print(f"{BAR}    {FROST_CYAN}/provider, /p{RESET}        Ganti penyedia AI & kelola API Key (Gemini, Groq, dll)")
    print(f"{BAR}    {FROST_CYAN}/cmodel, /m{RESET}          Pilih atau ganti model aktif untuk provider saat ini")
    print(f"{BAR}    {FROST_CYAN}/router [on|off]{RESET}     Universal workload auto-routing & fallback cerdas")
    print(f"{BAR}    {FROST_CYAN}/think [on|off]{RESET}      Visualisasi alur berpikir mendalam (<think> tags)")
    print(f"{BAR}    {FROST_CYAN}/consensus{RESET}           Mode konsensus multi-model secara paralel + juri AI")
    print(f"{BAR}    {FROST_CYAN}/registry [refresh]{RESET}  Katalog model OpenRouter live dari API")
    print(f"{BAR}")

    # Group 2: Code & Project Operations
    print(f"{BAR}  {FROST_AQUA}{BOLD}▣ Operasi Kode & Workspace{RESET}")
    print(f"{BAR}    {FROST_CYAN}/files{RESET}               Daftar semua file dalam workspace beserta ukurannya")
    print(f"{BAR}    {FROST_CYAN}/tree{RESET}                Visualisasi struktur folder interaktif")
    print(f"{BAR}    {FROST_CYAN}/find <glob>{RESET}         Cari file dengan pola glob (contoh: /find **/*.py)")
    print(f"{BAR}    {FROST_CYAN}/symbols <query>{RESET}     Cari fungsi, kelas, atau variabel di seluruh project")
    print(f"{BAR}    {FROST_CYAN}/diff{RESET}                Lihat git status dan uncommitted diff")
    print(f"{BAR}    {FROST_CYAN}/commit{RESET}              Otomatis buat AI commit message & jalankan git commit")
    print(f"{BAR}    {FROST_CYAN}/undo, /u{RESET}            Kembalikan (revert) perubahan file terakhir oleh AI")
    print(f"{BAR}    {FROST_CYAN}/copy, /cp [code|all]{RESET} Salin kode terakhir atau teks AI ke clipboard sistem")
    print(f"{BAR}    {FROST_CYAN}/todo{RESET}                Pindai komentar TODO & FIXME di seluruh workspace")
    print(f"{BAR}    {FROST_CYAN}/run [cmd]{RESET}           Jalankan runner project otomatis (python, npm, cargo)")
    print(f"{BAR}")

    # Group 3: Session & System
    print(f"{BAR}  {FROST_MINT}{BOLD}✚ Diagnostik & Sesi{RESET}")
    print(f"{BAR}    {FROST_CYAN}/doctor{RESET}              Pemeriksaan komprehensif sistem, API key, & jaringan")
    print(f"{BAR}    {FROST_CYAN}/usage, /stat{RESET}        Lacak konsumsi token, kecepatan (tok/s), & estimasi biaya")
    print(f"{BAR}    {FROST_CYAN}/history [clear]{RESET}    Lihat atau hapus riwayat percakapan sesi")
    print(f"{BAR}    {FROST_CYAN}/cd <path>{RESET}           Pindah direktori kerja aktif")
    print(f"{BAR}    {FROST_CYAN}/clear, /cls{RESET}         Bersihkan layar terminal & segarkan sesi")
    print(f"{BAR}    {FROST_CYAN}/exit, /quit, /q{RESET}     Keluar dari Klyro Code")
    _render_box_footer(74)


def show_features_guide() -> None:
    """Section 3: Key Features Deep Dive."""
    _render_box_header("Fitur Utama & Keunggulan KlyroCLI", 72)
    BAR = f"  {FROST_DARK}│{RESET}"

    print(f"{BAR}  {FROST_ICE}{BOLD}1. Universal Smart Router & Auto-Fallback{RESET}")
    print(f"{BAR}     Klyro mengklasifikasikan kompleksitas pertanyaan kamu secara otomatis.")
    print(f"{BAR}     Tugas ringan diarahkan ke model ultra-cepat (misal Groq LPU), dan tugas")
    print(f"{BAR}     arsitektur berat diarahkan ke model flagship. Jika kuota habis (429),")
    print(f"{BAR}     Klyro otomatis menawarkan auto-fallback ke provider alternatif.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_ICE}{BOLD}2. Multi-Model Consensus Engine (/consensus){RESET}")
    print(f"{BAR}     Mengirimkan pertanyaan coding kritis ke beberapa model sekaligus secara")
    print(f"{BAR}     paralel, kemudian AI Arbiter mengevaluasi dan memilih solusi terbaik.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_ICE}{BOLD}3. Zero-Risk Undo Manager (/undo){RESET}")
    print(f"{BAR}     Setiap kali AI membuat, mengedit, atau menghapus file, snapshot asli")
    print(f"{BAR}     disimpan di `.klyro/undo_snapshots/`. Kamu bisa membatalkan aksi AI")
    print(f"{BAR}     kapan saja cukup dengan mengetik {FROST_CYAN}/undo{RESET}.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_ICE}{BOLD}4. One-Click Clipboard Copy (/copy){RESET}")
    print(f"{BAR}     Ketik {FROST_CYAN}/copy{RESET} atau {FROST_CYAN}/cp{RESET} untuk langsung menyalin blok kode AI terakhir")
    print(f"{BAR}     ke clipboard tanpa perlu seleksi mouse. Mendukung Windows, Mac, Linux.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_ICE}{BOLD}5. Truecolor Syntax Highlighting & Shimmer Stream{RESET}")
    print(f"{BAR}     Tampilan terminal bergaya Nordic Frost dengan pewarnaan sintaks")
    print(f"{BAR}     otomatis untuk Python, JS, HTML, Bash, JSON, dll., serta live shimmer.")
    _render_box_footer(72)


def show_providers_guide() -> None:
    """Section 4: Multi-Provider & Free Tier Setup."""
    _render_box_header("Panduan Provider & Model Gratis", 72)
    BAR = f"  {FROST_DARK}│{RESET}"

    print(f"{BAR}  Klyro mendukung 8 AI Provider. Banyak di antaranya memiliki {FROST_MINT}Free Tier{RESET}:")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_CYAN}1. Google Gemini{RESET} {FROST_MINT}(Tingkat Gratis Tersedia){RESET}")
    print(f"{BAR}     Dapatkan API Key di: https://aistudio.google.com")
    print(f"{BAR}     Mendukung Gemini 1.5 Flash, 2.0 Flash, dan Pro dengan context 1M.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_CYAN}2. Groq LPU{RESET} {FROST_MINT}(Gratis, Kecepatan Ekstrem 500+ tok/s){RESET}")
    print(f"{BAR}     Dapatkan API Key di: https://console.groq.com")
    print(f"{BAR}     Sangat cocok untuk chat cepat, refactoring, dan linting instan.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_CYAN}3. OpenRouter{RESET} {FROST_MINT}(Model Gratis dengan tag :free){RESET}")
    print(f"{BAR}     Dapatkan API Key di: https://openrouter.ai/keys")
    print(f"{BAR}     Akses model seperti DeepSeek R1, Llama 3.3 70B secara gratis.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_CYAN}4. Anthropic Claude{RESET} {FROST_MINT}(Claude 3.7 Sonnet & 3.5 Haiku){RESET}")
    print(f"{BAR}     Dapatkan API Key di: https://console.anthropic.com")
    print(f"{BAR}     Model flagship untuk coding tingkat tinggi dan reasoning adaptif.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_CYAN}5. DeepSeek AI{RESET} {FROST_MINT}(DeepSeek V3 & DeepSeek R1){RESET}")
    print(f"{BAR}     Dapatkan API Key di: https://platform.deepseek.com")
    print(f"{BAR}     Kemampuan reasoning mendalam dan coding dengan biaya super hemat.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_CYAN}6. Local Ollama{RESET} {FROST_MINT}(100% Offline, Gratis, & Privat){RESET}")
    print(f"{BAR}     Jalankan 'ollama run qwen2.5-coder' di komputermu,")
    print(f"{BAR}     lalu pilih provider 'custom' di Klyro tanpa perlu API key.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_DARK}Gunakan {FROST_CYAN}/provider{FROST_DARK} untuk menyetel atau mengganti API Key kapan saja.{RESET}")
    _render_box_footer(72)


def show_tips_and_shortcuts() -> None:
    """Section 5: Shortcuts & Productivity Tips."""
    _render_box_header("Tips Produktivitas & Pintasan Keyboard", 72)
    BAR = f"  {FROST_DARK}│{RESET}"

    print(f"{BAR}  {FROST_MINT}• Mengetik Multi-line:{RESET}")
    print(f"{BAR}    Gunakan {FROST_WHITE}{BOLD}Alt + Enter{RESET} (atau {FROST_WHITE}Esc + Enter{RESET}) untuk membuat baris baru")
    print(f"{BAR}    saat menulis prompt panjang atau menempelkan error log bertingkat.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_MINT}• Memanggil Riwayat Prompt:{RESET}")
    print(f"{BAR}    Tekan tombol panah {FROST_WHITE}{BOLD}▲ (Atas){RESET} atau {FROST_WHITE}{BOLD}▼ (Bawah){RESET} untuk mengambil prompt")
    print(f"{BAR}    sebelumnya. Riwayat tersimpan permanen antar sesi CLI.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_MINT}• Membatalkan Streaming AI:{RESET}")
    print(f"{BAR}    Tekan {FROST_WHITE}{BOLD}ESC{RESET} atau {FROST_WHITE}{BOLD}Ctrl + C{RESET} untuk menghentikan respon AI seketika.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_MINT}• Perlindungan Git Otomatis (Dirty Tree Guard):{RESET}")
    print(f"{BAR}    Jika kamu memiliki perubahan kode yang belum di-commit, Klyro akan")
    print(f"{BAR}    mengingatkan dan menawarkan opsi auto-stash sebelum AI menulis file.")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_MINT}• Salin Kode Cepat:{RESET}")
    print(f"{BAR}    Ketik {FROST_CYAN}/cp{RESET} langsung setelah AI selesai menulis kode.")
    _render_box_footer(72)


def show_full_guide() -> None:
    """Show the entire documentation suite sequentially."""
    show_quickstart_guide()
    show_commands_guide()
    show_features_guide()
    show_providers_guide()
    show_tips_and_shortcuts()


# ── Topic registry ───────────────────────────────────────────
# Single source of truth: `/docs <topic>` routing and the interactive menu
# are both derived from DOC_TOPICS, so they can never drift apart.
DOC_TOPICS: dict[str, tuple[str, Callable[[], None]]] = {
    "quickstart": ("1. ⇈ Panduan Cepat (Quickstart)", show_quickstart_guide),
    "commands":   ("2. ✱ Daftar Perintah (/slash)",   show_commands_guide),
    "features":   ("3. ✦ Fitur Utama & Keunggulan",    show_features_guide),
    "providers":  ("4. ◍ Provider & Model Gratis",     show_providers_guide),
    "tips":       ("5. ✧ Tips & Pintasan Keyboard",    show_tips_and_shortcuts),
    "all":        ("6. ▤ Tampilkan Semua Panduan",     show_full_guide),
}

DOC_TOPIC_DESCRIPTIONS: dict[str, str] = {
    "quickstart": "Alur chatting, @file mention, & visual diff approval",
    "commands":   "Daftar referensi lengkap semua slash commands",
    "features":   "Smart Router, Auto-Fallback, Consensus, /undo, /copy",
    "providers":  "Panduan setup Gemini, Groq, OpenRouter Free, Ollama",
    "tips":       "Alt+Enter multiline, panah riwayat, !shell, safety",
    "all":        "Membaca seluruh dokumentasi secara berurutan",
}

# Accepted topic words → canonical topic id (English, Indonesian, and menu numbers).
TOPIC_ALIASES: dict[str, str] = {key: key for key in DOC_TOPICS}
TOPIC_ALIASES.update({
    "start": "quickstart", "mulai": "quickstart", "1": "quickstart",
    "command": "commands", "cmd": "commands", "perintah": "commands",
    "slash": "commands", "2": "commands",
    "feature": "features", "fitur": "features", "3": "features",
    "provider": "providers", "model": "providers", "models": "providers",
    "gratis": "providers", "free": "providers", "4": "providers",
    "tip": "tips", "shortcut": "tips", "shortcuts": "tips",
    "pintasan": "tips", "5": "tips",
    "full": "all", "semua": "all", "lengkap": "all", "6": "all",
})

# Topics that print a table of contents instead of a guide section.
HELP_TOPICS = ("help", "?", "-h", "--help", "topics", "list")

# Menu rows rendered by interactive_select().
MENU_OPTIONS: list[dict] = [
    {"label": label, "description": DOC_TOPIC_DESCRIPTIONS[key]}
    for key, (label, _renderer) in DOC_TOPICS.items()
]


def show_doc_topics() -> None:
    """Print the documentation table of contents (`/docs help`)."""
    _render_box_header("Topik Dokumentasi yang Tersedia", 72)
    BAR = f"  {FROST_DARK}│{RESET}"
    print(f"{BAR}  {FROST_GRAY}Pemakaian:{RESET} {FROST_CYAN}/docs <topik>{RESET} {FROST_DARK}│{RESET} {FROST_CYAN}/docs{RESET} {FROST_GRAY}menu interaktif{RESET}")
    print(f"{BAR}")
    for key, (label, _renderer) in DOC_TOPICS.items():
        print(f"{BAR}  {FROST_CYAN}{label}{RESET}")
        print(f"{BAR}      {FROST_DARK}/docs {key}{RESET} {FROST_GRAY}— {DOC_TOPIC_DESCRIPTIONS[key]}{RESET}")
    print(f"{BAR}")
    print(f"{BAR}  {FROST_GRAY}Alias angka juga diterima, contoh: {FROST_CYAN}/docs 1{RESET}")
    _render_box_footer(72)


def run_doc_command(args: str = "") -> None:
    """
    Main entrypoint for the /docs slash command.

    With a topic argument (quickstart, commands, features, providers, tips, all —
    plus Indonesian aliases and menu numbers) that section renders immediately;
    `/docs help` lists every available topic. With no argument an interactive
    arrow-key menu is presented instead.
    """
    topic = (args or "").strip().lower()

    if topic:
        if topic in HELP_TOPICS:
            show_doc_topics()
            return
        canonical = TOPIC_ALIASES.get(topic)
        if canonical is None:
            print(f"  {FROST_CORAL}✗{RESET} Topik dokumentasi tidak dikenal: {FROST_CYAN}{topic}{RESET}")
            print(f"  {FROST_DARK}Ketik {FROST_CYAN}/docs help{FROST_DARK} untuk daftar topik,{RESET}")
            print(f"  {FROST_DARK}atau {FROST_CYAN}/docs{FROST_DARK} untuk membuka menu interaktif.{RESET}\n")
            return
        DOC_TOPICS[canonical][1]()
        return

    # Interactive menu presentation
    selected_idx = interactive_select(
        "Klyro Code — Dokumentasi & Panduan Pengguna", MENU_OPTIONS, default_idx=0
    )
    if selected_idx < 0:
        print(f"  {FROST_DARK}Dokumentasi ditutup.{RESET}\n")
        return
    topic_ids = list(DOC_TOPICS)
    if 0 <= selected_idx < len(topic_ids):
        DOC_TOPICS[topic_ids[selected_idx]][1]()
