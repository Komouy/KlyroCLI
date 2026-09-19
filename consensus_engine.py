"""
consensus_engine.py — Klyro CLI Consensus Engine
Multi-model parallel querying + judge system dengan AI classifier.

Alur:
  1. classify_query()      → tanya model kecil: CODING atau CHAT?
  2. collect_candidates()  → ambil semua provider yang punya API key
  3. run_parallel()        → query setiap kandidat secara bersamaan (threading)
  4. judge()               → model terbaik yang tersedia mengevaluasi & mensintesis
  5. query()               → entry point dari klyro_cli.py
"""

import sys
import time
import threading

import provider_manager
from ai import OpenAICompatibleAssistant, GeminiAssistant, build_system_prompt
from errors import friendly

# ─────────────────────────────────────────────────────────────────
# ANSI COLORS (Nordic Frost — sama dengan klyro_cli.py)
# ─────────────────────────────────────────────────────────────────
RESET        = "\033[0m"
BOLD         = "\033[1m"
FROST_CYAN   = "\033[38;2;56;189;248m"
FROST_ICE    = "\033[38;2;186;230;253m"
FROST_MINT   = "\033[38;2;52;211;153m"
FROST_INDIGO = "\033[38;2;129;140;248m"
FROST_CORAL  = "\033[38;2;248;113;113m"
FROST_WHITE  = "\033[38;2;248;250;252m"
FROST_GRAY   = "\033[38;2;148;163;184m"
FROST_DARK   = "\033[38;2;71;85;105m"
FROST_AMBER  = "\033[38;2;251;191;36m"

# ─────────────────────────────────────────────────────────────────
# KONSTANTA
# ─────────────────────────────────────────────────────────────────
CANDIDATE_TIMEOUT = 90  # detik

# Judge priority: urutan provider yang dicoba sebagai judge
# Gemini Flash diprioritaskan (gratis, context 1M, cukup kuat)
JUDGE_PRIORITY = [
    ("gemini",    "gemini-3.6-flash"),     # gratis, context 1M, reliable
    ("gemini",    "gemini-2.5-pro"),       # lebih kuat kalau flash gagal
    ("deepseek",  "deepseek-reasoner"),
    ("openai",    "gpt-4o"),
    ("mistral",   "mistral-large-latest"),
    ("groq",      "llama-3.3-70b-specdec"),
    ("cerebras",  "llama-3.3-70b"),
    ("openrouter","deepseek/deepseek-r1:free"),
]

# Model flagship per provider (kandidat terkuat)
FLAGSHIP_MODELS = {
    "gemini":     "gemini-3.6-flash",          # model valid per 2025
    "groq":       "llama-3.3-70b-specdec",
    "cerebras":   "llama-3.3-70b",
    "openrouter": "deepseek/deepseek-r1:free",
    "mistral":    "mistral-large-latest",
    "deepseek":   "deepseek-reasoner",
    "openai":     "gpt-4o",
    "custom":     None,
}

# Fallback kalau hanya Gemini yang tersedia
GEMINI_FALLBACK_PAIR = [
    ("gemini", "gemini-3.6-flash"),
    ("gemini", "gemini-2.5-pro"),
]

# Model kecil/cepat untuk classifier — dipilih dari provider yang tersedia
# Urutan prioritas: gratis dulu, paling ringan dulu
CLASSIFIER_PRIORITY = [
    ("gemini",    "gemini-3.6-flash"),     # gratis, reliable, akurat
    ("cerebras",  "llama3.1-8b"),          # super cepat
    ("groq",      "llama-3.1-8b-instant"),       # cepat, gratis
    ("mistral",   "open-mistral-7b"),      # gratis tier
    ("openrouter","meta-llama/llama-3.3-70b-instruct:free"),
]

# Prompt classifier — ringkas, binary output
CLASSIFIER_PROMPT = """\
You are a query classifier for a coding assistant CLI.
Classify the user's message into exactly one of these two categories:

CODING — if the user wants to: write code, edit a file, debug an error, fix a bug,
         implement a feature, refactor, optimize, create a script, explain code in detail,
         analyze code logic, or do anything that requires generating or modifying code.

CHAT   — if the user wants to: ask a simple question, get a quick explanation of a concept,
         ask what a command does (without asking to change it), general conversation,
         or anything that does NOT require writing or changing code.

Respond with ONLY the single word: CODING or CHAT
No explanation. No punctuation. Just the word.

User message: {user_input}"""


# ─────────────────────────────────────────────────────────────────
# PROGRESS DISPLAY
# ─────────────────────────────────────────────────────────────────
class ConsensusProgressDisplay:
    """Real-time progress display untuk kandidat yang sedang berjalan."""

    def __init__(self, candidates: list[dict]):
        self.candidates = candidates
        self.statuses   = {i: "thinking" for i in range(len(candidates))}
        self.durations  = {i: 0.0 for i in range(len(candidates))}
        self._lock      = threading.Lock()
        self._lines_printed = 0

    def set_done(self, idx: int, duration: float, success: bool):
        with self._lock:
            self.statuses[idx]  = "done" if success else "error"
            self.durations[idx] = duration

    def _render_lines(self) -> list[str]:
        lines = []
        for i, cand in enumerate(self.candidates):
            prov  = cand["provider"].upper()[:7]
            model = cand["model"].split("/")[-1]  # strip prefix openrouter
            if len(model) > 28:
                model = model[:25] + "..."

            status = self.statuses[i]
            if status == "thinking":
                icon  = f"{FROST_CYAN}⟳{RESET}"
                label = f"{FROST_GRAY}thinking...{RESET}"
            elif status == "done":
                icon  = f"{FROST_MINT}✓{RESET}"
                label = f"{FROST_MINT}done ({self.durations[i]:.1f}s){RESET}"
            else:
                icon  = f"{FROST_CORAL}✗{RESET}"
                label = f"{FROST_CORAL}error/timeout{RESET}"

            lines.append(
                f"  {icon} {FROST_INDIGO}{prov:<8}{RESET} "
                f"{FROST_WHITE}{model:<30}{RESET} {label}"
            )
        return lines

    def print_initial(self):
        n = len(self.candidates)
        print(f"\n  {FROST_CYAN}{BOLD}◈ Consensus Mode{RESET} {FROST_DARK}— querying {n} candidates...{RESET}\n")
        lines = self._render_lines()
        for line in lines:
            print(line)
        self._lines_printed = len(lines)
        sys.stdout.flush()

    def refresh(self):
        with self._lock:
            # Hapus baris yang sudah dicetak
            for _ in range(self._lines_printed):
                sys.stdout.write("\033[F\033[K")
            lines = self._render_lines()
            for line in lines:
                print(line)
            self._lines_printed = len(lines)
            sys.stdout.flush()

    def finalize(self):
        self.refresh()
        print()  # baris kosong setelah status


# ─────────────────────────────────────────────────────────────────
# CONSENSUS ENGINE
# ─────────────────────────────────────────────────────────────────
class ConsensusEngine:

    def __init__(self, ai_assistant):
        self.ai = ai_assistant

    # ── 0. Classifier ────────────────────────────────────────────
    def classify_query(self, user_input: str) -> str:
        """
        Tanya model kecil/cepat: apakah query ini butuh CODING atau hanya CHAT?
        Return: "CODING" atau "CHAT"

        Mencoba semua CLASSIFIER_PRIORITY satu per satu sampai berhasil.
        Fallback ke "CODING" kalau semua gagal (lebih aman).
        """
        prompt = CLASSIFIER_PROMPT.format(user_input=user_input.strip())

        for prov, model in CLASSIFIER_PRIORITY:
            if not provider_manager.get_api_key(prov):
                continue  # skip provider tanpa API key

            try:
                if prov == "gemini":
                    clf = GeminiAssistant()
                    clf.current_model = model
                    clf.init_chat(".", "", 0, force_model=model)
                    raw = clf.tanya(prompt)
                else:
                    clf = OpenAICompatibleAssistant(prov)
                    clf.current_model = model
                    clf.init_chat(".", "", 0, force_model=model)
                    raw = clf.tanya(prompt)

                result = raw.strip().upper().split()[0] if raw.strip() else ""
                if result in ("CODING", "CHAT"):
                    return result
                # Jawaban tidak valid → coba provider berikutnya

            except Exception:
                continue  # provider ini gagal → coba berikutnya

        # Semua classifier gagal → default CODING (aman)
        return "CODING"

    # ── 1. Collect candidates ─────────────────────────────────────
    def collect_candidates(self) -> list[dict]:
        """
        Kumpulkan semua provider yang punya API key.
        Map ke flagship model masing-masing.
        Fallback ke 2 model Gemini kalau hanya ada 1 provider.
        """
        available = provider_manager.get_available_providers()

        # Kumpulkan kandidat (skip custom, skip provider tanpa flagship)
        candidates = []
        for prov in available:
            model = FLAGSHIP_MODELS.get(prov)
            if model:
                candidates.append({"provider": prov, "model": model})

        # Fallback: hanya 1 provider tersedia
        if len(candidates) <= 1:
            gemini_key = provider_manager.get_api_key("gemini")
            if gemini_key:
                candidates = [
                    {"provider": "gemini", "model": GEMINI_FALLBACK_PAIR[0][1]},
                    {"provider": "gemini", "model": GEMINI_FALLBACK_PAIR[1][1]},
                ]
            elif candidates:
                # Hanya ada 1 non-Gemini provider — jalankan langsung tanpa consensus
                return candidates  # akan di-handle di query() sebagai single candidate
            else:
                return []

        return candidates

    # ── 2. Build system prompt (reuse dari ai.py) ─────────────────
    def _get_system_prompt(self) -> str:
        folder = self.ai.folder_aktif or "."
        konteks = self.ai.konteks or ""
        return build_system_prompt(folder, konteks)

    # ── 3. Query satu kandidat (untuk thread) ────────────────────
    def _query_candidate(
        self,
        candidate: dict,
        user_input: str,
        results: list,
        idx: int,
        progress: ConsensusProgressDisplay,
    ):
        prov  = candidate["provider"]
        model = candidate["model"]
        t_start = time.time()
        success = False

        try:
            if prov == "gemini":
                assistant = GeminiAssistant()
                assistant.current_model = model
                ok, _ = assistant.init_chat(
                    self.ai.folder_aktif or ".",
                    self.ai.konteks or "",
                    self.ai.jumlah_file,
                    force_model=model,
                )
                if not ok:
                    raise RuntimeError("Failed to initialize Gemini")
                response = assistant.tanya(user_input)
            else:
                assistant = OpenAICompatibleAssistant(prov)
                assistant.current_model = model
                assistant.init_chat(
                    self.ai.folder_aktif or ".",
                    self.ai.konteks or "",
                    self.ai.jumlah_file,
                    force_model=model,
                )
                response = assistant.tanya(user_input)

            duration = time.time() - t_start

            if response and len(response.strip()) > 10:
                results[idx] = {
                    "provider": prov,
                    "model":    model,
                    "response": response,
                    "duration": duration,
                    "status":   "ok",
                }
                success = True
            else:
                results[idx] = {
                    "provider": prov, "model": model,
                    "response": "", "duration": duration,
                    "status": "empty",
                }

        except Exception as e:
            duration = time.time() - t_start
            results[idx] = {
                "provider": prov, "model": model,
                "response": "", "duration": duration,
                "status": friendly("error", e),
            }

        finally:
            progress.set_done(idx, time.time() - t_start, success)

    # ── 4. Run parallel ───────────────────────────────────────────
    def run_parallel(
        self,
        user_input: str,
        candidates: list[dict],
    ) -> list[dict]:
        """
        Jalankan semua kandidat secara paralel menggunakan threading.
        Main thread update progress display tiap 0.3 detik.
        """
        n = len(candidates)
        results = [None] * n
        progress = ConsensusProgressDisplay(candidates)

        threads = []
        for i, cand in enumerate(candidates):
            t = threading.Thread(
                target=self._query_candidate,
                args=(cand, user_input, results, i, progress),
                daemon=True,
            )
            threads.append(t)

        # Tampilkan progress awal
        progress.print_initial()

        # Start semua thread
        for t in threads:
            t.start()

        # Monitor sampai semua selesai atau timeout
        deadline = time.time() + CANDIDATE_TIMEOUT
        while True:
            all_done = all(r is not None for r in results)
            if all_done:
                break
            if time.time() > deadline:
                # Tandai yang belum selesai sebagai timeout
                for i, r in enumerate(results):
                    if r is None:
                        results[i] = {
                            "provider": candidates[i]["provider"],
                            "model":    candidates[i]["model"],
                            "response": "",
                            "duration": CANDIDATE_TIMEOUT,
                            "status":   "timeout",
                        }
                        progress.set_done(i, CANDIDATE_TIMEOUT, False)
                break
            time.sleep(0.3)
            progress.refresh()

        progress.finalize()
        return results

    # ── 5. Build judge prompt ─────────────────────────────────────
    def build_judge_prompt(
        self,
        user_input: str,
        results: list[dict],
    ) -> str:
        valid = [r for r in results if r and r.get("status") == "ok"]

        candidates_text = ""
        for i, r in enumerate(valid, 1):
            label = f"{r['provider'].upper()} • {r['model']}"
            candidates_text += (
                f"\n--- Candidate {i} ({label}) ---\n"
                f"{r['response']}\n"
            )

        folder  = self.ai.folder_aktif or "."
        konteks = self.ai.konteks or "[No project context loaded]"

        return (
            "You are an expert code review judge for a CLI coding assistant called Klyro.\n\n"
            f"You received {len(valid)} candidate responses to the user's question below.\n"
            "Your job is to synthesize the BEST answer by:\n"
            "1. Identifying the most accurate and complete solution\n"
            "2. Combining the strongest parts from each candidate if they complement each other\n"
            "3. Fixing any errors or incomplete code you notice\n"
            "4. Responding in the SAME LANGUAGE the user used\n\n"
            "IMPORTANT: Do NOT mention that you are a judge or that you reviewed multiple "
            "candidates — just give the best answer directly.\n\n"
            f"USER QUESTION:\n{user_input}\n\n"
            f"PROJECT CONTEXT ({folder}):\n"
            f"{konteks[:6000]}{'...[truncated]' if len(konteks) > 6000 else ''}\n\n"
            f"CANDIDATE RESPONSES:{candidates_text}\n"
            "Now provide the best synthesized answer:"
        )

    # ── 6. Pick judge ─────────────────────────────────────────────
    def _pick_judge(self) -> tuple[str, str] | None:
        """
        Pilih judge terbaik yang tersedia berdasarkan JUDGE_PRIORITY.
        Return (provider, model) atau None kalau tidak ada.
        """
        for prov, model in JUDGE_PRIORITY:
            key = provider_manager.get_api_key(prov)
            if key:
                return prov, model
        return None

    # ── 7. Judge (streaming) ──────────────────────────────────────
    def judge(self, user_input: str, results: list[dict]):
        """
        Stream jawaban final dari judge.
        Fallback ke jawaban kandidat terpanjang kalau judge gagal.
        """
        valid = [r for r in results if r and r.get("status") == "ok"]

        # Hanya 1 kandidat berhasil → langsung pakai tanpa judge
        if len(valid) == 1:
            print(
                f"  {FROST_AMBER}◈{RESET} {FROST_GRAY}1 candidate — "
                f"skipping judge, using directly{RESET}\n"
            )
            yield valid[0]["response"]
            return

        # Tidak ada kandidat berhasil → fallback ke ai_assistant biasa
        if len(valid) == 0:
            print(
                f"  {FROST_CORAL}◈{RESET} {FROST_GRAY}All candidates failed — "
                f"falling back to direct query{RESET}\n"
            )
            yield from self.ai.tanya_stream(user_input)
            return

        # Pilih judge
        judge_info = self._pick_judge()
        if not judge_info:
            # Tidak ada provider untuk judge — pakai jawaban terpanjang
            best = max(valid, key=lambda r: len(r.get("response", "")))
            print(
                f"  {FROST_AMBER}◈{RESET} {FROST_GRAY}No judge provider available — "
                f"using longest candidate ({best['provider'].upper()}){RESET}\n"
            )
            yield best["response"]
            return

        judge_prov, judge_model = judge_info
        judge_prompt = self.build_judge_prompt(user_input, results)

        print(
            f"  {FROST_INDIGO}◈{RESET} {FROST_GRAY}Judge{RESET} "
            f"{FROST_WHITE}({judge_prov.upper()} • {judge_model}){RESET} "
            f"{FROST_GRAY}synthesizing...{RESET}\n"
        )

        try:
            if judge_prov == "gemini":
                judge_assistant = GeminiAssistant()
                judge_assistant.current_model = judge_model
                ok, _ = judge_assistant.init_chat(
                    self.ai.folder_aktif or ".",
                    "",  # konteks sudah ada di judge_prompt
                    0,
                    force_model=judge_model,
                )
                if not ok:
                    raise RuntimeError("Failed to initialize Gemini judge")
                yield from judge_assistant.tanya_stream(judge_prompt)
            else:
                judge_assistant = OpenAICompatibleAssistant(judge_prov)
                judge_assistant.current_model = judge_model
                judge_assistant.init_chat(".", "", 0, force_model=judge_model)
                yield from judge_assistant.tanya_stream(judge_prompt)

        except Exception as e:
            # Fallback ke jawaban terpanjang
            best = max(valid, key=lambda r: len(r.get("response", "")))
            print(
                f"\n  {FROST_CORAL}◈ Judge error: {e}{RESET} "
                f"— using longest candidate ({best['provider'].upper()})\n"
            )
            yield best["response"]

    # ── 8. Main entry point ───────────────────────────────────────
    def query(self, user_input: str):
        """
        Entry point utama — dipanggil dari klyro_cli.py sebagai pengganti
        ai_assistant.tanya_stream(user_input).

        Alur:
          1. classify_query()  → CODING atau CHAT?
          2. CHAT              → langsung ke ai_assistant (cepat, 1 model)
          3. CODING            → consensus: run_parallel() + judge()

        Yields string chunks yang bisa langsung di-stream ke terminal.
        """
        # ── Step 1: Classify ──────────────────────────────────────
        query_type = self.classify_query(user_input)

        if query_type == "CHAT":
            # Pertanyaan ringan — langsung ke model aktif, tanpa overhead
            print(
                f"  {FROST_DARK}⟳ Chat mode • {self.ai.current_model}{RESET}\n"
            )
            yield from self.ai.tanya_stream(user_input)
            return

        # ── Step 2: CODING — jalankan consensus ───────────────────
        candidates = self.collect_candidates()

        # Tidak ada kandidat (tidak ada API key)
        if not candidates:
            print(
                f"  {FROST_CORAL}◈{RESET} {FROST_GRAY}No providers configured — "
                f"type /provider to add an API key{RESET}\n"
            )
            yield from self.ai.tanya_stream(user_input)
            return

        # Hanya 1 kandidat → langsung tanpa consensus
        if len(candidates) == 1:
            print(
                f"  {FROST_AMBER}◈{RESET} {FROST_GRAY}Coding mode — 1 provider, "
                f"skipping consensus{RESET}\n"
            )
            yield from self.ai.tanya_stream(user_input)
            return

        # Jalankan parallel query ke semua kandidat
        results = self.run_parallel(user_input, candidates)

        # Stream jawaban judge
        yield from self.judge(user_input, results)
